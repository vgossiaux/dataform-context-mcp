function normalize(col) {
  return `LOWER(TRIM(${col}))`;
}

module.exports = { normalize };
