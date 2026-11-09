import { defineConfig } from 'vite';
import { createVuePlugin } from 'vite-plugin-vue2';
import { serverOptions } from './tooling/serverOptions';
export default defineConfig(({ command }) => {
    // Building static browser assets needs no credentials or running database.
    const common = {
        plugins: [createVuePlugin()],
        resolve: { dedupe: ['vue'] },
    };
    if (command === 'build')
        return common;
    // Project scripts inject MySQL's public settings; standalone npm uses local defaults.
    const options = serverOptions(process.env);
    return {
        ...common,
        server: options,
        preview: options,
    };
});
