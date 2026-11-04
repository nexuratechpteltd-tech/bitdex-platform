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
  async headers() {
    return [
      {
        source: '/api/:path*',
        headers: [
          { key: 'X-Robots-Tag', value: 'noindex, nofollow, noarchive' },
        ],
      },
      {
        source: '/trading/api/:path*',
        headers: [
          { key: 'X-Robots-Tag', value: 'noindex, nofollow, noarchive' },
        ],
      },
      {
        source: '/(.*)',
        headers: [
          { key: 'X-Frame-Options', value: 'SAMEORIGIN' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
        ],
      },
    ];
  },
  async rewrites() {
    return [
      {
        source: '/api/v1/:path*',
        destination: 'http://127.0.0.1:8002/api/v1/:path*',
      },
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
