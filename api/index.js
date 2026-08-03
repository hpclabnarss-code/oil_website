const express = require('express');
const app = express();

// Your routes (e.g., /api/admin/login, /api/admin/spills)
app.use(express.json());

app.get('/api/index', (req, res) => {
  res.status(200).json({ message: "API is working" });
});

module.exports = app;