import sys, os, smtplib
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

host = os.environ.get('SMTP_HOST')
port = int(os.environ.get('SMTP_PORT', 587))
user = os.environ.get('SMTP_USER')
password = os.environ.get('SMTP_PASSWORD')
sender = os.environ.get('SMTP_FROM')

to = sys.argv[1] if len(sys.argv) > 1 else user

print(f"Host:   {host}:{port}")
print(f"User:   {user}")
print(f"From:   {sender}")
print(f"To:     {to}")
print(f"Key:    {password[:12]}... (hidden)")
print()

try:
    print("1. Connecting...")
    server = smtplib.SMTP(host, port, timeout=15)
    server.set_debuglevel(1)  # verbose SMTP conversation
    
    print("2. EHLO...")
    server.ehlo()
    
    print("3. STARTTLS...")
    server.starttls()
    server.ehlo()
    
    print("4. LOGIN...")
    server.login(user, password)
    
    print("5. SENDING...")
    msg = f"From: {sender}\r\nTo: {to}\r\nSubject: AutoPress SMTP Verbose Test\r\n\r\nThis is a verbose test email from AutoPress. If you see this, it works!\r\n"
    result = server.sendmail(sender, [to], msg)
    print(f"   Result: {result}")
    
    server.quit()
    print("\n✅ Email sent successfully!")
    
except smtplib.SMTPAuthenticationError as e:
    print(f"\n❌ AUTH ERROR: {e}")
except smtplib.SMTPRecipientsRefused as e:
    print(f"\n❌ RECIPIENT REFUSED: {e}")
except smtplib.SMTPSenderRefused as e:
    print(f"\n❌ SENDER REFUSED: {e}")
except Exception as e:
    print(f"\n❌ ERROR ({type(e).__name__}): {e}")
