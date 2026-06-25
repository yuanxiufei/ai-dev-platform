import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import vue from "@vitejs/plugin-vue"
import Components from "unplugin-vue-components/vite"
import { defineConfig } from "vite"

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  plugins: [
    vue(),
    tailwindcss(),
    Components({
      dirs: [
        path.resolve(__dirname, "src/components"),
        path.resolve(__dirname, "src/layouts"),
      ],
      extensions: ["vue"],
      deep: true,
      dts: path.resolve(__dirname, "src/components.d.ts"),
    }),
  ],
  server: {
    port: 5176,
  },
})
