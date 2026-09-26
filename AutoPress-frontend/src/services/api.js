const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000';

/**
 * Sends up to 5 PDF files to /process-pdf-template and returns a Blob URL for preview and download.
 * @param {File[]} pdfFiles Array of up to 5 File objects
 * @returns {Promise<{ blobUrl: string, blob: Blob, filename: string }>}
 */
export async function processPdfTemplate(pdfFiles) {
  if (!pdfFiles || pdfFiles.length === 0) {
    throw new Error('Please select at least 1 PDF file (up to 5 maximum).');
  }

  if (pdfFiles.length > 5) {
    throw new Error('You can only upload a maximum of 5 PDF files at once.');
  }

  const formData = new FormData();
  pdfFiles.forEach((file, index) => {
    // Backend expects keys: pdf_1, pdf_2, pdf_3, pdf_4, pdf_5
    formData.append(`pdf_${index + 1}`, file);
  });

  console.log(`[AutoPress] Submitting ${pdfFiles.length} file(s) to: ${API_BASE_URL}/process-pdf-template`);

  let response;
  try {
    response = await fetch(`${API_BASE_URL}/process-pdf-template`, {
      method: 'POST',
      body: formData,
    });
  } catch (netErr) {
    console.error('[AutoPress] Network/Fetch Error:', netErr);
    throw new Error(
      `Failed to connect to ${API_BASE_URL}. ` +
      `Please check: (1) Did you restart the Vite dev server ("npm run dev") after updating .env? ` +
      `(2) In your browser, open DevTools (F12) -> Console/Network to view the specific CORS/network error.`
    );
  }

  if (!response.ok) {
    let errorMessage = `Server returned status ${response.status}`;
    try {
      const errorJson = await response.json();
      if (errorJson && errorJson.error) {
        errorMessage = errorJson.error;
      }
    } catch {
      const errorText = await response.text();
      if (errorText) {
        errorMessage = errorText;
      }
    }
    throw new Error(errorMessage);
  }

  const blob = await response.blob();
  const blobUrl = URL.createObjectURL(blob);

  // Extract filename from Content-Disposition if present
  let filename = 'fayda_id_cards.png';
  const disposition = response.headers.get('content-disposition');
  if (disposition && disposition.includes('filename=')) {
    const match = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
    if (match && match[1]) {
      filename = match[1].replace(/['"]/g, '');
    }
  }

  return { blobUrl, blob, filename };
}

