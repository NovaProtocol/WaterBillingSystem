const fs = require('fs');
const path = require('path');
const out = path.join(__dirname, '..', 'src', 'buildTime.ts');
fs.writeFileSync(out, `export const BUILD_TIMESTAMP = ${Date.now()};\n`);
