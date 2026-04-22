/**
 * Express Server
 * Backend API for Financial Research Analyst
 */

import express, { Request, Response, NextFunction, ErrorRequestHandler } from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import path from 'path';
import analysisRoutes from './routes/analysis.js';

// Load environment variables — .env lives at project root (analyst/), one level above backend/
dotenv.config({ path: path.resolve(process.cwd(), '../.env') });
dotenv.config(); // fallback: also try ./. env in case CWD is already the project root

const app = express();
const PORT = process.env.PORT || 3001;

// Middleware
app.use(cors({
  credentials: true,
  origin: (origin, callback) => {
    const allowedOrigins = [
      'http://localhost:3000',
      'http://127.0.0.1:3000',
      'http://localhost:5173',
      'http://127.0.0.1:5173',
      /\.vercel\.app$/,
      process.env.FRONTEND_URL
    ].filter(Boolean) as (string | RegExp)[];
    if (!origin || allowedOrigins.some((allowed) => (allowed instanceof RegExp ? allowed.test(origin) : allowed === origin))) {
      return callback(null, true);
    }
    return callback(new Error(`CORS blocked for origin: ${origin}`));
  }
}));
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Routes
app.use('/api', analysisRoutes);

// Health check endpoint
app.get('/api/health', (req: Request, res: Response) => {
  res.json({
    status: 'ok',
    message: 'Financial Research Analyst API is running',
    timestamp: new Date().toISOString()
  });
});

// Root endpoint
app.get('/', (req: Request, res: Response) => {
  res.json({
    message: 'Financial Research Analyst API',
    version: '2.0.0',
    endpoints: {
      health: '/api/health',
      analyze: 'POST /api/analyze',
      analyzeStream: 'POST /api/analyze/stream'
    }
  });
});

// Error handling middleware
const errorHandler: ErrorRequestHandler = (err: Error, req: Request, res: Response, next: NextFunction) => {
  console.error('Error:', err);
  const status = (err as any).status || 500;
  res.status(status).json({
    status: 'error',
    message: err.message || 'Internal server error',
    error: process.env.NODE_ENV === 'development' ? err.stack : undefined
  });
};

app.use(errorHandler);

// Start server
app.listen(PORT, () => {
  console.log(`\n${'='.repeat(60)}`);
  console.log(`Financial Research Analyst API Server`);
  console.log(`${'='.repeat(60)}`);
  console.log(`Server running on http://localhost:${PORT}`);
  console.log(`Health check: http://localhost:${PORT}/api/health`);
  console.log(`${'='.repeat(60)}\n`);
});

