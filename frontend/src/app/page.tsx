import { redirect } from "next/navigation";

export default function Home() {
  // Middleware already forces auth; if we reach here we're authed.
  redirect("/dashboard");
}
