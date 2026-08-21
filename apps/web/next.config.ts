import path from 'node:path';
import type {NextConfig} from 'next';

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Монорепо: standalone-сборка должна трассировать зависимости от КОРНЯ репозитория,
  // иначе Next возьмёт apps/web за корень и не положит в бандл общие node_modules.
  outputFileTracingRoot: path.join(__dirname, '../..'),
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: false,
  },
  // Allow access to remote image placeholder.
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'picsum.photos',
        port: '',
        pathname: '/**', // This allows any path under the hostname
      },
    ],
  },
  /**
   * Старый адрес раздела не отдаётся в 404.
   *
   * `/corpus` разошёлся по закладкам, ссылкам в переписке и по чужим вкладкам,
   * открытым прямо сейчас. Переименование раздела — наше решение, а платить за
   * него разорванной ссылкой пришлось бы читателю. Постоянный редирект стоит
   * трёх строк и снимает вопрос навсегда.
   */
  async redirects() {
    return [
      {source: '/corpus', destination: '/dataset', permanent: true},
      {source: '/corpus/:path*', destination: '/dataset/:path*', permanent: true},
    ];
  },
  output: 'standalone',
  transpilePackages: ['motion'],
  webpack: (config, {dev}) => {
    // HMR is disabled in AI Studio via DISABLE_HMR env var.
    // Do not modifyâfile watching is disabled to prevent flickering during agent edits.
    if (dev && process.env.DISABLE_HMR === 'true') {
      config.watchOptions = {
        ignored: /.*/,
      };
    }
    return config;
  },
};

export default nextConfig;
