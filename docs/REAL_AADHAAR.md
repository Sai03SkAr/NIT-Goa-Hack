# Testing with a real Aadhaar

TrueID can verify a real Aadhaar **offline**, the way UIDAI and RBI intend: through the **Secure QR** printed on Aadhaar letters, PVC cards and e-Aadhaar PDFs issued since 2019. Nothing is sent to UIDAI, and no Aadhaar number is stored in full.

Code: `backend/app/modules/document/aadhaar.py`, wired into the document, face and registry steps. Tests: `backend/tests/test_aadhaar.py`.

## What is in the Secure QR

The QR holds one large decimal number. Decoded and decompressed, it contains:

- the name, date of birth, gender, care-of, full address and pincode
- the **last 4** Aadhaar digits and the time the QR was generated
- (newer versions) the last 4 digits of the mobile
- a small JPEG2000 photo
- SHA-256 hashes of the linked mobile and email
- an RSA-2048 signature by UIDAI over all of it

## What TrueID checks

| Check | How |
|---|---|
| Issuer signature | The UIDAI signature verifies against UIDAI's public certificate. Any edit to any field breaks it. |
| QR agrees with the printed card | The printed lines are read (the layout isn't TrueID's template, so every line is read) and must show the signed name, date of birth and last 4 digits. If the print can't be read, a person compares; it is never an automatic forgery verdict. |
| Form agrees with the card | The typed name and date of birth match the signed values. For the ID, the last 4 digits must match. |
| Selfie matches the card photo | The face printed on the card, found anywhere on the image. |
| Selfie matches the issuer's photo | **UIDAI's own photo from the signed QR.** This is the strongest face check: the photo can't be swapped without breaking the signature. |
| Identity in the issuer registry | The demo registry doesn't know real people, so UIDAI's signature is the registry answer (`REG_UIDAI_ATTESTED`). |
| Tax ID (PAN) linked | Shown as *could not check*: the demo tax registry only holds test identities. In production this is the NSDL/Protean PAN API. |
| Mobile linked to this Aadhaar | The typed mobile is hashed the way UIDAI does and compared with the hash in the QR. This is context only, because people change numbers. |

Expect **REVIEW**, not APPROVE, for a real person on this demo: PAN can't be verified, and liveness needs the live webcam. That is the correct, honest outcome.

## Step by step

1. **Get UIDAI's public certificate.** UIDAI publishes the certificate used to sign Secure QR and offline e-KYC data in its developer and ecosystem documentation on uidai.gov.in (see the Secure QR Code Reader and Aadhaar Paperless Offline e-KYC pages). Save the `.cer` (or `.pem`) file as `data/issuer_keys/uidai/uidai.cer`. Several certificates can sit in that folder (UIDAI rotates keys); any one that verifies is accepted. Alternatively, set `TRUEID_UIDAI_CERT=/path/to/cert`. Restart the backend.
   - **Without the certificate**, the QR is still read and the details compared, but the signature shows *could not check*, never *valid*.
2. **Photograph the right side.** Use the Aadhaar letter, or a printout of the e-Aadhaar PDF, where the photo, the details and the Secure QR are on the same page. For a PVC card, put the front and back side by side in one photo. Make the QR sharp and fill the frame; glare on the QR is the usual failure. TrueID reads dense QRs with zxing-cpp (`pip install zxing-cpp`).
3. **Fill in the KYC form at `/kyc`** with your real details. Type your full 12-digit Aadhaar number; only its last 4 digits are compared with the QR.
4. **Take the live selfie and do the head-turn check** on the webcam.
5. **Open the case** in the analyst console. The Document tab shows *UIDAI signature valid*, the Secure QR format, whether the mobile is the linked one, and the printed text read. The Face tab shows UIDAI's photo next to your selfie.

## Privacy

- **Last 4 digits only.** The QR itself contains only the last 4 Aadhaar digits. The typed number is stored masked (`XXXX XXXX 1234`) and keyed-hashed for the graph, never in full.
- **The UIDAI photo** is saved as a short-lived upload, deleted after the retention period like other uploads, and erased with **Erase applicant data**.
- **Mobile and email hashes** are compared and never stored.
- **Test only with your own Aadhaar.** Erase the case afterwards from the case page. That also removes its network signals.
- **Pre-2019 QRs** are plain, unsigned XML. TrueID reads them but reports the signature as *could not check*.
