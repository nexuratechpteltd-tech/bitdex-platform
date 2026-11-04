import { MetadataRoute } from 'next';

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: '*',
      allow: '/',
      disallow: [
        '/api/',
        '/trading/api/',
        '/saas/',
        '/admin/',
        '/dashboard/',
        '/portal/',
        '/_next/data/',
      ],
    },
    sitemap: 'https://bitdex.ltd/sitemap.xml',
  };
}
