import { Logo } from "@/components/Brand";
import { OpsConsole } from "@/components/OpsConsole";

export default function Ops() {
  return <OpsConsole brand={<Logo />} profileNote="Northstar runs full KYC: OTPs, NSDL, DigiLocker, live selfie, signature and eSign." />;
}
