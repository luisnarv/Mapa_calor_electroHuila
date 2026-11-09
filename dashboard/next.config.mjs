/** @type {import('next').NextConfig} */
const nextConfig = {
  // El Dockerfile fija NEXT_OUTPUT=standalone para generar una imagen mínima;
  // sin la variable (npm run dev/build local, Vercel) todo sigue igual.
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  // El navegador integrado abre el servidor de desarrollo por 127.0.0.1.
  allowedDevOrigins: ["127.0.0.1"]
};

export default nextConfig;
