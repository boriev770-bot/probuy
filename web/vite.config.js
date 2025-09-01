export default {
  server: {
    host: '0.0.0.0',
    port: 5173
  },
  build: {
    rollupOptions: {
      input: {
        index: 'index.html',
        scan: 'scan.html'
      }
    }
  }
}
