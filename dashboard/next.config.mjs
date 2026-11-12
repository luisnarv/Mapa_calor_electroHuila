/** @type {import('next').NextConfig} */
const nextConfig = {
  // El navegador integrado abre el servidor de desarrollo por 127.0.0.1.
  allowedDevOrigins: ["127.0.0.1"],

  // Puente hacia el backend del asistente. El servidor del backend solo habla HTTP y Vercel sirve por
  // HTTPS, así que el navegador bloquearía la llamada directa (contenido mixto). Con
  // `NEXT_PUBLIC_API_URL=/backend` el navegador llama a su propio dominio y Next reenvía al servidor.
  // `BACKEND_URL` cambia el destino sin tocar el código (ver DESPLIEGUE.md).
  async rewrites() {
    const destino = (process.env.BACKEND_URL || "http://52.88.48.137/mapa-electrohuila").replace(/\/+$/, "");
    return [{ source: "/backend/:path*", destination: `${destino}/:path*` }];
  }
};

export default nextConfig;
