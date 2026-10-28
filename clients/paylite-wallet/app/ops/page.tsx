import { Logo } from "@/components/Brand";
import { OpsConsole } from "@/components/OpsConsole";

export default function Ops() {
  return <OpsConsole brand={<Logo />} profileNote="PayLite runs minimum KYC: mobile OTP only, with self-declared details and uploaded photos. TrueID is the only identity check." />;
}
