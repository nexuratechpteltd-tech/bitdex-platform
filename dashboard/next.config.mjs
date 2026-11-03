/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
  async rewrites() {
    return [
      {
        source: '/api/backend/:path*',
        destination: 'http://127.0.0.1:8002/api/v1/:path*',
      },
      {
        source: '/trading/api/backend/:path*',
        destination: 'http://127.0.0.1:8002/api/v1/:path*',
      },
      {
        source: '/trading',
        destination: '/',
      },
      {
        source: '/trading/:path*',
        destination: '/:path*',
      },
    ];
  },
};

export default nextConfig;
