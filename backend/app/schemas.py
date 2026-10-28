"""Shared module output shape + the fixed reason-code table. The LLM may only cite these codes."""
from typing import Any
from pydantic import BaseModel, Field

REASONS: dict[str, str] = {
    # document
    "DOC_QR_MISSING": "No readable signed QR on the ID card",
    "DOC_QR_SIG_INVALID": "QR signature does not verify against the issuer key",
    "DOC_QR_OCR_MISMATCH": "Printed details do not match the issuer-signed QR code",
    "DOC_FORM_MISMATCH": "Details typed in the form do not match the ID card",
    "DOC_CHECKSUM_FAIL": "ID number fails the Verhoeff checksum",
    "DOC_PAN_FORMAT": "Tax ID (PAN) format or holder-type check failed",
    "DOC_DATE_INVALID": "Dates on the card are impossible (DOB/issue/age)",
    "DOC_FORENSIC_ANOMALY": "Image forensics found local inconsistencies (edges/font/noise)",
    "DOC_TRUFOR_HIGH": "TruFor forgery detector flags manipulation",
    "DOC_EXIF_EDITOR": "Image metadata shows an editing tool",
    "DOC_LAYOUT_DRIFT": "Text is off the template's expected positions",
    "DOC_QR_UNVERIFIABLE": "The QR's signature could not be checked (unknown or missing issuer key)",
    "DOC_OCR_UNREADABLE": "Printed card text was too unclear to compare with the signed QR",
    "DOC_GENAI_METADATA": "Card image metadata names an AI image generator",
    "IMG_QUALITY_LOW": "Photos too blurry, noisy or unclear to verify reliably; ask for a retake",
    # biometric
    "BIO_CARD_FACE_MISMATCH": "Selfie does not match the card portrait",
    "BIO_REGISTRY_FACE_MISMATCH": "Selfie does not match the issuer's registry photo",
    "BIO_FACE_REUSED": "This face already applied under a different name",
    "BIO_LIVENESS_FAIL": "Active liveness challenge failed",
    "BIO_VIRTUAL_CAMERA": "A virtual camera (injection tool) was detected",
    "BIO_FRAMES_INCONSISTENT": "Liveness frames are not one live person turning their head",
    "BIO_SCREEN_REPLAY": "Selfie looks like a screen/photo replay (blur/moire)",
    "BIO_NO_FACE": "No face found in the selfie or card",
    "BIO_MEDIA_REUSED": "This exact selfie picture was already submitted in an earlier application",
    "BIO_GENAI_METADATA": "Selfie metadata names an AI image generator",
    "BIO_LIVENESS_NOT_PROVIDED": "No server-verified liveness: the selfie was uploaded, not captured live",
    "BIO_CHALLENGE_INVALID": "The liveness challenge was expired, reused or issued to another session",
    "BIO_CHALLENGE_FRAMES": "Wrong number of liveness frames for the challenge",
    "BIO_FRAMES_DUPLICATE": "Liveness frames are copies of one still image",
    "BIO_NO_MOTION": "Liveness frames show no continuous head movement (looks like still photos, not a live turn)",
    "BIO_FRAME_FACE_COUNT": "A liveness frame shows no face or more than one face",
    "BIO_VOICE_LOW": "Voice check score low (simulated, never used in the decision)",
    # behavior
    "BEH_FAST_FILL": "Form filled faster than a human plausibly can",
    "BEH_PASTE_HEAVY": "Most fields were pasted, not typed",
    "BEH_ROBOTIC_TIMING": "Keystroke timing is near-constant (scripted)",
    "BEH_VELOCITY_DEVICE": "This device submitted many applications recently",
    "BEH_VELOCITY_IP": "This IP submitted many applications recently",
    "BEH_VELOCITY_PHONE": "This phone number is on several recent applications",
    "BEH_EMAIL_SEQUENCE": "Email follows a sequential pattern seen on other identities",
    "BEH_KEYSTROKE_LINK": "Typing rhythm matches a different identity",
    "BEH_ANOMALY": "Session behaviour is anomalous vs genuine users",
    # registry
    "REG_ID_NOT_FOUND": "ID number not found in the identity registry",
    "REG_NAME_MISMATCH": "Name differs from the identity registry",
    "REG_DOB_MISMATCH": "Date of birth differs from the identity registry",
    "REG_PAN_LINK_MISMATCH": "PAN is not linked to this ID number",
    "REG_PAN_NOT_FOUND": "PAN not found in the tax registry",
    "REG_PAN_PERSON_MISMATCH": "PAN holder's name or date of birth differs from the applicant",
    "REG_UNAVAILABLE": "Registry could not be reached; identity is unverified, not disproven",
    "REG_SIM_NEW": "Phone SIM activated very recently",
    "REG_SIM_NAME_MISMATCH": "Phone is registered to someone else",
    "REG_NO_CKYC": "No prior KYC record anywhere",
    "REG_THIN_FILE": "Credit file is thin for the stated age",
    "REG_INQUIRY_BURST": "Burst of recent credit inquiries (bust-out pattern)",
    # correlation
    "COR_RING_MEMBER": "Part of a densely linked cluster of identities",
    "COR_SHARED_DEVICE": "Device shared with other identities",
    "COR_SHARED_PHONE": "Phone shared with other identities",
    "COR_SHARED_ID": "ID number used by another applicant",
    "COR_MULE_HERDING": "This device onboarded several different people this week (possible mule recruitment)",
    "COR_FAMILY_PATTERN": "Shared address/phone looks like a family (suspicion reduced)",
    # policy
    "MODEL_UNAVAILABLE": "Risk model not loaded or out of date; a human decides",
}

STATUS_TEXT = {"FAIL": "failed", "UNAVAILABLE": "could not be checked", "NOT_PROVIDED": "was not provided",
               "SIMULATED": "is simulated"}


def code_text(code: str) -> str:
    """Text for any code, including the policy's EV_<CHECK>_<STATUS> evidence codes."""
    if code in REASONS:
        return REASONS[code]
    if code.startswith("EV_"):
        from app.policy import REQUIRED
        for st, word in STATUS_TEXT.items():
            if code.endswith("_" + st):
                check = code[3:-len(st) - 1].lower()
                return f"{REQUIRED.get(check, (check,))[0]}: {word}"
    return code


class Reason(BaseModel):
    code: str
    text: str = ""
    weight: float = 0.0

    def model_post_init(self, _):
        if not self.text:
            self.text = code_text(self.code)


class ModuleResult(BaseModel):
    module: str
    risk: float = 0.0
    confidence: float = 1.0
    reasons: list[Reason] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    features: dict[str, float] = Field(default_factory=dict)  # numeric features for fusion
    simulated: bool = False
    latency_ms: int = 0


def reason(code: str, weight: float) -> Reason:
    return Reason(code=code, weight=round(float(weight), 3))
