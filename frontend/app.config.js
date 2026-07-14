const path = require('path');

require('dotenv').config({
  path: path.resolve(__dirname, '..', '.env'),
  override: true,
});

module.exports = require('./app.json');
