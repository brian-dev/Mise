/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Transpile the shared workspace package so its TS source is bundled directly.
  transpilePackages: ["@mise/shared"],
};

export default nextConfig;
