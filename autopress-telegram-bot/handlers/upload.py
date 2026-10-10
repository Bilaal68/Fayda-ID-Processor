"""
PDF Upload & PNG Processing Handler

Handles document uploads, file validation, balance pre-checks,
temporary file management, backend API processing invocation,
and print-ready PNG image delivery.
"""

import io
import os
import tempfile
from telegram import Update
from telegram.ext import ContextTypes
from keyboards import get_main_menu_keyboard, get_cancel_keyboard
from services import user_service, credit_service, job_service
from states.conversation_states import ConversationState
from utils.validators import validate_pdf_metadata, validate_pdf_bytes
from utils.logger import setup_logger

logger = setup_logger(__name__)


async def upload_init_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles when the user initiates upload via /upload command or '📤 Upload' button.
    Checks credit balance first. If 0, prompts user to buy credits.
    If credits available, transitions to WAITING_FOR_PDF state.
    """
    if not update.effective_user or not update.effective_message:
        return

    user_id = update.effective_user.id
    user_service.get_or_create_user(
        telegram_user_id=user_id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name,
        last_name=update.effective_user.last_name
    )

    current_state = context.user_data.get("state", ConversationState.IDLE.name)
    if current_state == ConversationState.PROCESSING.name:
        await update.effective_message.reply_text(
            "⏳ Your previous PDF is still being processed.\n\n"
            "Please wait for it to finish."
        )
        return

    balance = credit_service.get_balance(user_id)
    logger.info("User %s initiated upload flow. Current balance: %d", user_id, balance)

    context.user_data.pop("selected_package", None)
    context.user_data.pop("payment_method", None)
    context.user_data.pop("submitting_payment", None)

    if balance < 1:
        context.user_data["state"] = ConversationState.IDLE.name
        await update.effective_message.reply_text(
            "❌ You don't have enough credits.\n\n"
            "Please tap 🛒 Buy Credits below to top up your balance.",
            reply_markup=get_main_menu_keyboard()
        )
        return

    context.user_data["state"] = ConversationState.WAITING_FOR_PDF.name
    await update.effective_message.reply_text(
        "📸 Please send your Fayda ID PDF.\n\n"
        "I will process it and return the print-ready image.",
        reply_markup=get_cancel_keyboard()
    )


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles cancellation of the current flow."""
    if not update.effective_message:
        return

    current_state = context.user_data.get("state", ConversationState.IDLE.name)
    if current_state == ConversationState.PROCESSING.name:
        await update.effective_message.reply_text(
            "⏳ Your previous PDF is still being processed.\n\n"
            "Please wait for it to finish."
        )
        return

    context.user_data["state"] = ConversationState.IDLE.name
    context.user_data.pop("selected_package", None)
    context.user_data.pop("payment_method", None)
    context.user_data.pop("submitting_payment", None)
    logger.info("User %s cancelled operation", update.effective_user.id if update.effective_user else "Unknown")
    await update.effective_message.reply_text(
        "Operation cancelled.",
        reply_markup=get_main_menu_keyboard()
    )


async def document_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles incoming documents when user sends a PDF file.
    Validates file format, size, header bytes, manages temporary files,
    and coordinates backend processing with PNG image delivery.
    """
    if not update.effective_user or not update.effective_message:
        return

    user_id = update.effective_user.id
    current_state = context.user_data.get("state", ConversationState.IDLE.name)

    # 1. Check if user is already processing another PDF
    if current_state == ConversationState.PROCESSING.name:
        logger.info("User %s sent a document while job is already PROCESSING", user_id)
        await update.effective_message.reply_text(
            "⏳ Your previous PDF is still being processed.\n\n"
            "Please wait for it to finish."
        )
        return

    # Route to payment screenshot handler if user is submitting payment receipt
    if current_state in (ConversationState.WAITING_FOR_PAYMENT_SCREENSHOT.name, ConversationState.WAITING_FOR_RECEIPT.name):
        from handlers.credits import payment_screenshot_handler
        await payment_screenshot_handler(update, context)
        return

    # 2. Check for text cancel triggers
    if update.effective_message.text and update.effective_message.text in ("❌ Cancel", "/cancel", "Cancel", "cancel"):
        await cancel_handler(update, context)
        return


    document = update.effective_message.document

    # 3. Reject non-documents or invalid uploads
    if not document:
        logger.warning("User %s sent non-document attachment", user_id)
        await update.effective_message.reply_text(
            "❌ Please send a PDF file.",
            reply_markup=get_cancel_keyboard() if current_state == ConversationState.WAITING_FOR_PDF.name else get_main_menu_keyboard()
        )
        return

    # 4. Validate metadata (filename extension, MIME type, size limit)
    meta_valid, meta_err = validate_pdf_metadata(
        file_name=document.file_name,
        file_size=document.file_size,
        mime_type=document.mime_type
    )

    if not meta_valid:
        logger.warning("User %s document metadata validation failed: %s (%s)", user_id, document.file_name, meta_err)
        await update.effective_message.reply_text(
            "❌ Please send a PDF file.",
            reply_markup=get_cancel_keyboard() if current_state == ConversationState.WAITING_FOR_PDF.name else get_main_menu_keyboard()
        )
        return

    # 5. Authoritative credit check before downloading or heavy processing
    balance = credit_service.get_balance(user_id)
    if balance < 1:
        context.user_data["state"] = ConversationState.IDLE.name
        await update.effective_message.reply_text(
            "❌ You don't have enough credits.\n\n"
            "Please buy credits first.",
            reply_markup=get_main_menu_keyboard()
        )
        return

    logger.info("PDF received from User ID: %s (file: %s, size: %s bytes)", user_id, document.file_name, document.file_size)

    # 6. ALWAYS immediately acknowledge receipt BEFORE long backend request
    ack_msg = await update.effective_message.reply_text(
        "⏳ Your PDF has been received.\n\n"
        "Processing your Fayda ID...\n"
        "Please wait."
    )

    # Mark user in PROCESSING state to prevent concurrent submissions
    context.user_data["state"] = ConversationState.PROCESSING.name

    temp_input_path = None
    try:
        # 7. Download the Telegram file to secure temporary storage
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            temp_input_path = tmp_file.name

        tg_file = await document.get_file()
        await tg_file.download_to_drive(custom_path=temp_input_path)
        logger.info("Telegram file downloaded to temporary path: %s", temp_input_path)

        # Read downloaded bytes for deep validation
        with open(temp_input_path, "rb") as f:
            pdf_bytes = f.read()

        # 8. Deep validate magic bytes (%PDF-)
        bytes_valid, bytes_err = validate_pdf_bytes(pdf_bytes)
        if not bytes_valid:
            logger.warning("User %s document content validation failed: %s", user_id, bytes_err)
            context.user_data["state"] = ConversationState.IDLE.name
            await ack_msg.edit_text(
                "❌ Processing failed.\n\n"
                "Your credit was not deducted.\n"
                "Please try again.",
                reply_markup=get_main_menu_keyboard()
            )
            return

        # 9. Update progress message
        try:
            await ack_msg.edit_text(
                "⏳ Processing your Fayda ID...\n\n"
                "This may take a little while. Please don't send another PDF."
            )
        except Exception:
            pass

        # 10. Execute Job Service Pipeline (calls existing backend API)
        safe_filename = os.path.basename(document.file_name or "fayda.pdf")
        success, error_reason, result_png_bytes, remaining_balance = await job_service.process_pdf_upload(
            telegram_user_id=user_id,
            pdf_bytes=pdf_bytes,
            filename=safe_filename
        )

        context.user_data["state"] = ConversationState.IDLE.name

        # 11. Handle Result
        if not success or not result_png_bytes:
            logger.error("Job execution failed for User ID: %s. Reason: %s", user_id, error_reason)
            
            if error_reason and "timed out" in str(error_reason).lower():
                await ack_msg.edit_text(
                    "⚠️ Processing is taking longer than expected.\n\n"
                    "Please try again in a moment.",
                    reply_markup=get_main_menu_keyboard()
                )
            else:
                await ack_msg.edit_text(
                    "❌ Processing failed.\n\n"
                    "Your credit was not deducted.\n"
                    "Please try again.",
                    reply_markup=get_main_menu_keyboard()
                )
            return

        # 12. Send Success Notification and Resulting PNG Image
        try:
            await ack_msg.edit_text(
                "✅ Processing completed!\n\n"
                "Your Fayda ID image is ready."
            )
        except Exception:
            pass

        # Send lossless 300 DPI PNG image file
        output_stream = io.BytesIO(result_png_bytes)
        output_stream.name = "fayda_id_cards.png"

        await update.effective_message.reply_document(
            document=output_stream,
            filename="fayda_id_cards.png",
            caption="🖼️ Your Fayda ID image"
        )

        # Send remaining balance message
        await update.effective_message.reply_text(
            f"💰 Your remaining credits: {remaining_balance}",
            reply_markup=get_main_menu_keyboard()
        )

    except Exception as exc:
        context.user_data["state"] = ConversationState.IDLE.name
        logger.error("Unhandled exception during PDF processing for User ID: %s: %s", user_id, exc, exc_info=True)
        try:
            await ack_msg.edit_text(
                "❌ Processing failed.\n\n"
                "Your credit was not deducted.\n"
                "Please try again.",
                reply_markup=get_main_menu_keyboard()
            )
        except Exception:
            await update.effective_message.reply_text(
                "❌ Processing failed.\n\n"
                "Your credit was not deducted.\n"
                "Please try again.",
                reply_markup=get_main_menu_keyboard()
            )

    finally:
        # Clean up temporary downloaded file
        if temp_input_path and os.path.exists(temp_input_path):
            try:
                os.remove(temp_input_path)
                logger.info("Cleaned up temporary upload file: %s", temp_input_path)
            except Exception as e:
                logger.warning("Failed to remove temporary file %s: %s", temp_input_path, e)


async def generic_non_document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catches photos, audio, stickers, or text during upload or idle state."""
    if not update.effective_message or not update.effective_user:
        return

    text = update.effective_message.text
    if text and text in ("❌ Cancel", "/cancel", "Cancel", "cancel"):
        await cancel_handler(update, context)
        return

    state = context.user_data.get("state", ConversationState.IDLE.name)
    if state == ConversationState.PROCESSING.name:
        await update.effective_message.reply_text(
            "⏳ Your previous PDF is still being processed.\n\n"
            "Please wait for it to finish."
        )
        return

    # 1. If in payment screenshot upload state
    if state in (ConversationState.WAITING_FOR_PAYMENT_SCREENSHOT.name, ConversationState.WAITING_FOR_RECEIPT.name):
        if update.effective_message.photo or update.effective_message.document:
            from handlers.credits import payment_screenshot_handler
            await payment_screenshot_handler(update, context)
            return
        else:
            from keyboards import get_payment_waiting_keyboard
            await update.effective_message.reply_text(
                "❌ Please send a screenshot image (photo or image document) of your completed payment.",
                reply_markup=get_payment_waiting_keyboard()
            )
            return

    # 2. If in package selection state
    if state == ConversationState.WAITING_FOR_PACKAGE_SELECTION.name:
        from keyboards import get_packages_keyboard
        await update.effective_message.reply_text(
            "⚠️ Please select a package from the options below, or tap Back / Cancel:",
            reply_markup=get_packages_keyboard()
        )
        return

    # 3. If in payment method selection state
    if state == ConversationState.WAITING_FOR_PAYMENT_METHOD.name:
        from keyboards import get_payment_methods_keyboard
        await update.effective_message.reply_text(
            "⚠️ Please select a payment method from the options below, or tap Back / Cancel:",
            reply_markup=get_payment_methods_keyboard()
        )
        return

    # 4. If photo, voice, video, sticker, or waiting for PDF
    msg = update.effective_message
    if msg.photo or msg.video or msg.audio or msg.voice or msg.sticker or state == ConversationState.WAITING_FOR_PDF.name:
        await update.effective_message.reply_text(
            "❌ Please send a PDF file.",
            reply_markup=get_cancel_keyboard() if state == ConversationState.WAITING_FOR_PDF.name else get_main_menu_keyboard()
        )
        return

    # 5. Unrecognized text in IDLE state: guide user to persistent main menu
    if state == ConversationState.IDLE.name and text:
        await update.effective_message.reply_text(
            "💡 Please select an option from the menu below, or send /help for assistance.",
            reply_markup=get_main_menu_keyboard()
        )

