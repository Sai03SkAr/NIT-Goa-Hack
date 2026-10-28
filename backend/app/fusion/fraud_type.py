"""Fraud-type classifier: rules over the signal pattern, with a fixed recommended action (SentiLink idea)."""

ACTIONS = {
    "first_party": ("First-party / Frankenstein", "Verify via issuer OTP / face authentication"),
    "third_party": ("Third-party fabricated", "Require DigiLocker-fetched document or assisted video KYC"),
    "ring": ("Synthetic ring", "Freeze linked applications, escalate to the fraud team"),
    "bot": ("Bot / scripted", "Block device, step-up challenge"),
    "tampered": ("Tampered document", "Reject document, request re-upload through DigiLocker"),
    "injection": ("Injection / replay", "Assisted video KYC"),
    "incomplete": ("Verification incomplete", "Run a live selfie (liveness) check before granting full access"),
    "none": ("No fraud pattern", "Proceed"),
}


def classify(f: dict) -> str:
    """Strongest, most specific evidence first: cryptographic/document proof, injection, graph, then softer signals."""
    from app.modules.biometric.face import threshold
    g = lambda k, d=0.0: f.get(k, d) if f.get(k, d) == f.get(k, d) else d  # NaN -> default
    if g("doc_qr_missing", 1) == 0 and g("doc_sig_invalid") == 0 and (g("doc_qr_ocr_dob", 1) == 0 or g("doc_qr_ocr_name", 1) < 0.8):
        return "tampered"
    if g("doc_sig_invalid") and g("reg_id_found", 1):
        return "tampered"  # counterfeit card for a real identity
    if g("bio_virtual_cam"):
        return "injection"
    if g("cor_ring_score") > 0 or (g("bio_face_reuse_diff_name") > 0 and g("cor_comp_size") >= 3) or g("beh_email_seq") > 0:
        return "ring"
    if (g("beh_fill_time", 99) < 20 and g("beh_paste_frac") >= 0.6) or g("beh_iki_cv", 1) < 0.15 or g("beh_vel_device_24h") >= 3:
        return "bot"
    if not g("bio_liveness_pass", 1):
        return "injection"
    if g("reg_id_found") == 0:
        return "third_party"
    if g("bio_sim_registry", 1) < threshold() or g("reg_name_sim", 1) < 0.8 or g("doc_sig_invalid"):
        return "first_party"
    if g("doc_forensic") > 0.6:
        return "tampered"
    if g("reg_sim_age_days", 999) < 30 and g("reg_ckyc", 1) == 0:
        return "third_party"
    if g("bio_liveness_performed", 1) == 0:
        return "incomplete"
    return "none"


def action(ft: str) -> dict:
    label, act = ACTIONS[ft]
    return {"type": ft, "label": label, "action": act}
