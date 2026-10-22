import "@copilotkit/react-core/v2/styles.css";
import "./globals.css";

export const metadata = { title: "Chat with memory, tools and skills" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
