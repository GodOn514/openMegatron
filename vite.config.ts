import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import fs from 'fs';
import net from 'net';
import { defineConfig, loadEnv } from 'vite';
import { parse } from 'smol-toml';

async function getFreePort(startPort: number): Promise<number> {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.listen(startPort, '0.0.0.0', () => {
      server.once('close', () => resolve(startPort));
      server.close();
    });
    server.on('error', () => {
      resolve(getFreePort(startPort + 1));
    });
  });
}

export default defineConfig(async ({ mode }) => {
  const env = loadEnv(mode, '.', '');

  let targetPort = 3000;
  try {
    const tomlPath = path.resolve(__dirname, './config.toml'); 
    if (fs.existsSync(tomlPath)) {
      const tomlStr = fs.readFileSync(tomlPath, 'utf-8');
      const config = parse(tomlStr) as any;
      if (config.frontend && config.frontend.port) {
        targetPort = Number(config.frontend.port);
      }
    }
  } catch (err) {}

  if (env.VITE_FRONTEND_PORT || process.env.FRONTEND_PORT) {
    targetPort = Number(env.VITE_FRONTEND_PORT || process.env.FRONTEND_PORT) || targetPort;
  }

  const actualFreePort = await getFreePort(targetPort);

  return {
    plugins: [react(), tailwindcss()],
    define: {
      'process.env.GEMINI_API_KEY': JSON.stringify(env.GEMINI_API_KEY),
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    server: {
      port: actualFreePort,
      host: '0.0.0.0',
      strictPort: true, 
      hmr: process.env.DISABLE_HMR !== 'true',
      watch: {
        ignored: [
          '**/.docker-cli/**',
          '**/.npm-cache/**',
          '**/.npm-home/**',
          '**/.runtime/**',
          '**/dist/**',
          '**/docs/**',
          '**/log/**',
          '**/pysrc/**',
          '**/scripts/**',
          '**/tests/**',
          '**/venv/**',
          '**/README.md',
          '**/docker-compose.yml',
        ],
      },
    },
  };
});
