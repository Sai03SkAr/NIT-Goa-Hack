/** What an applicant is told. Safe by design: it says what to do next, never which check fired
 * (naming the check would teach a fraudster what to fix). Technical reasons stay in the analyst console. */
export type ApplicantMessage = { title: string; body: string; action?: { label: string; href: string } };

export function applicantMessage(band: string | undefined, codes: string[]): ApplicantMessage {
  const has = (p: string) => codes.some((c) => c.startsWith(p));
  if (band === "APPROVE") {
    return { title: "You're verified", body: "Your identity has been confirmed. You can continue to your account." };
  }
  if (band === "REVIEW") {
    if (codes.includes("IMG_QUALITY_LOW") || codes.includes("EV_CAPTURE_QUALITY_FAIL")) {
      return { title: "Your photos weren't clear enough",
        body: "Please retake them in good light, holding the card flat and the camera steady.",
        action: { label: "Retake photos", href: "/kyc" } };
    }
    if (codes.includes("EV_LIVENESS_NOT_PROVIDED")) {
      return { title: "We need a quick live face check",
        body: "An uploaded photo can't show us it's really you right now. Please do the short face check with your camera, or wait and a member of our team will review your application.",
        action: { label: "Do the face check", href: "/kyc" } };
    }
    if (codes.includes("BIO_LIVENESS_FAIL") || codes.includes("EV_LIVENESS_FAIL") || codes.includes("EV_LIVENESS_UNAVAILABLE")) {
      return { title: "We couldn't complete the face check",
        body: "Please try again in good light, facing the camera, with only you in the frame. It takes under a minute.",
        action: { label: "Retake face check", href: "/kyc" } };
    }
    if (has("BIO_CARD_FACE") || has("BIO_REGISTRY_FACE")) {
      return { title: "We need to take a closer look at your photo",
        body: "A member of our team will compare your selfie with your ID, usually within one working day. You don't need to do anything now." };
    }
    return { title: "Your application is being reviewed",
      body: "Some details need a quick manual check. We'll update you within one working day. You don't need to do anything now." };
  }
  if (band === "REJECT") {
    if (has("DOC_")) {
      return { title: "We couldn't verify your ID card",
        body: "Please upload a clear photo of your original card, or fetch your ID securely from DigiLocker instead.",
        action: { label: "Start again", href: "/kyc" } };
    }
    return { title: "We couldn't verify your identity online",
      body: "You can still complete verification through a short assisted video call, or at a branch with your original documents." };
  }
  return { title: "Checking your application", body: "This usually takes a few seconds." };
}
