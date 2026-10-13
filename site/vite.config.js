import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base './' : GitHub Pages 처럼 저장소 이름이 경로에 붙는 주소(/레포명/)에서도 자원 경로가 깨지지 않게 한다.
export default defineConfig({
  base: './',
  plugins: [react()],
})
