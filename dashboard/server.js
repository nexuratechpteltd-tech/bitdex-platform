const http = require('http');
const next = require('next');

const port = parseInt(process.env.PORT, 10) || 33900;
const app = next({ dev: false, dir: __dirname });
const handle = app.getRequestHandler();

app.prepare().then(() => {
  http.createServer((req, res) => {
    handle(req, res);
  }).listen(port, '127.0.0.1', (err) => {
    if (err) throw err;
    console.log(`> Bitdex Staging Dashboard HTTP active internally on http://127.0.0.1:${port}`);
  });
}).catch((err) => {
  console.error('Failed to prepare Next.js app:', err);
  process.exit(1);
});
