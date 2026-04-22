import express, { Request, Response } from 'express';
import multer from 'multer';
import path from 'path';
import { promises as fs } from 'fs';
import { MongoClient, GridFSBucket, ObjectId } from 'mongodb';
import { runAnalysis, runQueryResolution, runDocumentPreview, ProgressData, AnalysisResult, QueryResolution } from '../services/pythonService.js';

const router = express.Router();
const upload = multer({
  dest: path.resolve(process.cwd(), 'tmp_uploads'),
  limits: { fileSize: 10 * 1024 * 1024 }, // 10MB
  fileFilter: (req, file, cb) => {
    if (file.mimetype === 'application/pdf' || file.originalname.toLowerCase().endsWith('.pdf')) {
      cb(null, true);
      return;
    }
    cb(new Error('Only PDF uploads are supported'));
  }
});

interface AnalyzeRequest {
  ticker: string;
  horizon: string;
  risk_profile: string;
}

interface AnalyzeFormRequest {
  ticker?: string;
  horizon?: string;
  risk_profile?: string;
}

interface ErrorResponse {
  status: 'error';
  message: string;
  error?: string;
}

interface SuccessResponse {
  status: 'success';
  data: AnalysisResult;
  timing: Record<string, number>;
}

let mongoClient: MongoClient | null = null;
async function getDb() {
  if (!mongoClient) {
    const uri = process.env.MONGODB_URI;
    if (!uri) throw new Error('MONGODB_URI is required');
    mongoClient = new MongoClient(uri);
    await mongoClient.connect();
  }
  return mongoClient.db('vantage');
}

async function uploadTempFileToGridFS(file: Express.Multer.File) {
  const db = await getDb();
  const bucket = new GridFSBucket(db, { bucketName: 'pdfs' });
  const filename = `${Date.now()}-${(file.originalname || 'uploaded.pdf').replace(/[^a-zA-Z0-9._-]/g, '_')}`;
  const uploadStream = bucket.openUploadStream(filename, {
    metadata: { originalName: file.originalname, mimeType: file.mimetype }
  });
  const bytes = await fs.readFile(file.path);
  uploadStream.end(bytes);
  await new Promise((resolve, reject) => {
    uploadStream.on('finish', resolve);
    uploadStream.on('error', reject);
  });
  await fs.unlink(file.path).catch(() => undefined);
  return uploadStream.id.toString();
}

/**
 * POST /api/resolve-query
 * Resolves a natural language query to a stock ticker symbol
 */
router.post('/resolve-query', async (req: Request, res: Response) => {
  try {
    const { query } = req.body;

    if (!query || typeof query !== 'string' || !query.trim()) {
      return res.status(400).json({
        status: 'error',
        message: 'Missing required field: query'
      });
    }

    // If it already looks like a ticker (1-5 uppercase alphanumeric), return immediately
    const trimmed = query.trim().toUpperCase();
    if (/^[A-Z]{1,5}(-[A-Z]{1,2})?$/.test(trimmed)) {
      return res.json({
        ticker: trimmed,
        original_query: query,
        resolved: false,
        confidence: 1.0
      });
    }

    console.log(`[API] Resolving query: "${query}"`);
    const result: QueryResolution = await runQueryResolution(query.trim());

    res.json(result);
  } catch (error: any) {
    console.error('[API] Query resolution error:', error);
    res.status(500).json({
      status: 'error',
      message: error.message || 'Query resolution failed',
      ticker: null,
      resolved: false,
      confidence: 0
    });
  }
});

/**
 * POST /api/analyze
 * Standard analysis endpoint (returns results after completion)
 */
router.post('/analyze', upload.single('document'), async (req: Request<{}, SuccessResponse | ErrorResponse, AnalyzeRequest | AnalyzeFormRequest>, res: Response<SuccessResponse | ErrorResponse>) => {
  try {
    const { ticker, horizon, risk_profile } = req.body as AnalyzeRequest;

    // Validate input
    if (!ticker || !horizon || !risk_profile) {
      return res.status(400).json({
        status: 'error',
        message: 'Missing required fields: ticker, horizon, risk_profile'
      });
    }

    const validHorizons = ['short', 'medium', 'long'] as const;
    const validRiskProfiles = ['conservative', 'moderate', 'aggressive'] as const;

    if (!validHorizons.includes(horizon.toLowerCase() as typeof validHorizons[number])) {
      return res.status(400).json({
        status: 'error',
        message: `Invalid horizon. Must be one of: ${validHorizons.join(', ')}`
      });
    }

    if (!validRiskProfiles.includes(risk_profile.toLowerCase() as typeof validRiskProfiles[number])) {
      return res.status(400).json({
        status: 'error',
        message: `Invalid risk_profile. Must be one of: ${validRiskProfiles.join(', ')}`
      });
    }

    console.log(`[API] Starting analysis for ${ticker.toUpperCase()}...`);

    // Run analysis
    let gridfsFileId: string | undefined;
    const persistedDocumentName = req.file?.originalname;
    if (req.file?.path) {
      gridfsFileId = await uploadTempFileToGridFS(req.file);
    }

    const result = await runAnalysis(
      ticker.toUpperCase(),
      horizon.toLowerCase(),
      risk_profile.toLowerCase(),
      null,
      {
        uploadedDocumentPath: gridfsFileId,
        uploadedDocumentName: persistedDocumentName
      }
    );

    // Format response
    res.json({
      status: 'success',
      data: result,
      timing: result.timing || {}
    });

  } catch (error: any) {
    console.error('[API] Analysis error:', error);
    res.status(500).json({
      status: 'error',
      message: error.message || 'Analysis failed',
      error: process.env.NODE_ENV === 'development' ? error.stack : undefined
    });
  } finally {
    if (req.file?.path) {
      fs.unlink(req.file.path).catch(() => undefined);
    }
  }
});

/**
 * POST /api/analyze/stream
 * Streaming analysis endpoint with Server-Sent Events (SSE)
 * Provides real-time progress updates
 */
router.post('/analyze/stream', upload.single('document'), async (req: Request<{}, void, AnalyzeRequest | AnalyzeFormRequest>, res: Response) => {
  try {
    let gridfsFileId: string | undefined;
    const persistedDocumentName = req.file?.originalname;
    if (req.file?.path) {
      gridfsFileId = await uploadTempFileToGridFS(req.file);
    }

    const { ticker, horizon, risk_profile } = req.body as AnalyzeRequest;

    // Validate input
    if (!ticker || !horizon || !risk_profile) {
      return res.status(400).json({
        status: 'error',
        message: 'Missing required fields: ticker, horizon, risk_profile'
      });
    }

    const validHorizons = ['short', 'medium', 'long'] as const;
    const validRiskProfiles = ['conservative', 'moderate', 'aggressive'] as const;

    if (!validHorizons.includes(horizon.toLowerCase() as typeof validHorizons[number])) {
      return res.status(400).json({
        status: 'error',
        message: `Invalid horizon. Must be one of: ${validHorizons.join(', ')}`
      });
    }

    if (!validRiskProfiles.includes(risk_profile.toLowerCase() as typeof validRiskProfiles[number])) {
      return res.status(400).json({
        status: 'error',
        message: `Invalid risk_profile. Must be one of: ${validRiskProfiles.join(', ')}`
      });
    }

    // Set up SSE headers
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('Access-Control-Allow-Origin', '*');

    console.log(`[API] Starting streaming analysis for ${ticker.toUpperCase()}...`);
    console.log(`[API] Request headers:`, {
      'user-agent': req.headers['user-agent'],
      'accept': req.headers['accept'],
      'connection': req.headers['connection']
    });

    // Send initial progress message immediately to keep connection alive
    res.write(`event: progress\n`);
    res.write(`data: ${JSON.stringify({
      step: 'system',
      message: `Starting analysis for ${ticker.toUpperCase()}...`,
      timestamp: Date.now()
    })}\n\n`);

    // Set up keep-alive interval to prevent connection timeout
    // Send a comment every 15 seconds to keep connection alive (more frequent)
    const keepAliveInterval = setInterval(() => {
      if (!connectionAlive || responseEnded) {
        clearInterval(keepAliveInterval);
        return;
      }
      
      // Check if response is still writable
      if (res.destroyed || res.closed || res.writableEnded) {
        connectionAlive = false;
        responseEnded = true;
        clearInterval(keepAliveInterval);
        return;
      }
      
      try {
        // Send keep-alive with timestamp for debugging
        const timestamp = Date.now();
        res.write(`: keep-alive ${timestamp}\n\n`);
        // Log occasionally for debugging
        if (Math.random() < 0.05) { // Log ~5% of keep-alives
          console.log(`[API] Sent keep-alive message (${timestamp})`);
        }
      } catch (error: any) {
        // Connection closed, clear interval
        connectionAlive = false;
        responseEnded = true;
        clearInterval(keepAliveInterval);
        console.log('[API] Keep-alive failed:', error.message);
      }
    }, 15000); // Every 15 seconds (more frequent to prevent timeouts)

    // Track if connection is still alive
    let connectionAlive = true;
    let responseEnded = false;
    
    // Check connection status - use both req and res events
    // Note: req.close can fire prematurely, so we check res.writableEnded before marking as closed
    req.on('close', () => {
      // Only mark as closed if response is also not writable
      if (connectionAlive && (res.writableEnded || res.destroyed || res.closed)) {
        connectionAlive = false;
        responseEnded = true;
        clearInterval(keepAliveInterval);
        console.log('[API] Client disconnected from stream (req.close) - Python process may still be running');
      } else if (connectionAlive) {
        // req.close fired but response is still writable - might be a false positive
        console.log('[API] req.close fired but response still writable - continuing...');
      }
    });
    
    res.on('close', () => {
      if (connectionAlive) {
        connectionAlive = false;
        responseEnded = true;
        clearInterval(keepAliveInterval);
        console.log('[API] Response closed (res.close) - Python process may still be running');
      }
    });
    
    res.on('finish', () => {
      connectionAlive = false;
      responseEnded = true;
      clearInterval(keepAliveInterval);
      console.log('[API] Response finished');
    });
    
    // Also check for errors
    res.on('error', (error: Error) => {
      console.error('[API] Response error:', error);
      connectionAlive = false;
      responseEnded = true;
      clearInterval(keepAliveInterval);
    });

    // Progress callback to send SSE events
    const sendProgress = (progressData: ProgressData) => {
      // Double-check connection status before sending
      if (responseEnded) {
        return;
      }
      
      // Check if response is still writable (more reliable than connectionAlive flag)
      if (res.destroyed || res.closed || res.writableEnded) {
        if (connectionAlive) {
          connectionAlive = false;
          responseEnded = true;
          clearInterval(keepAliveInterval);
          console.log('[API] Response is no longer writable - stopping progress updates');
        }
        return;
      }
      
      // Update connectionAlive flag if we successfully write
      if (!connectionAlive && !responseEnded) {
        connectionAlive = true; // Re-enable if we can write
      }
      
      try {
        res.write(`event: progress\n`);
        res.write(`data: ${JSON.stringify(progressData)}\n\n`);
        // Only log important progress messages to reduce noise
        if (progressData.step !== 'system' || progressData.message.includes('Agent')) {
          console.log(`[API] Sent progress: ${progressData.step} - ${progressData.message.substring(0, 50)}...`);
        }
      } catch (error: any) {
        console.error('[API] Error sending progress:', error.message);
        connectionAlive = false;
        responseEnded = true;
        clearInterval(keepAliveInterval);
      }
    };

    // Run analysis with progress callbacks
    runAnalysis(
      ticker.toUpperCase(),
      horizon.toLowerCase(),
      risk_profile.toLowerCase(),
      sendProgress,
      {
        uploadedDocumentPath: gridfsFileId,
        uploadedDocumentName: persistedDocumentName
      }
    )
      .then((result: AnalysisResult) => {
        if (req.file?.path) {
          fs.unlink(req.file.path).catch(() => undefined);
        }
        clearInterval(keepAliveInterval);
        // Send completion event
        res.write(`event: complete\n`);
        res.write(`data: ${JSON.stringify({
          status: 'success',
          data: result,
          timing: result.timing || {}
        })}\n\n`);
        res.end();
      })
      .catch((error: Error) => {
        if (req.file?.path) {
          fs.unlink(req.file.path).catch(() => undefined);
        }
        clearInterval(keepAliveInterval);
        console.error('[API] Analysis error:', error);
        // Send error event
        res.write(`event: error\n`);
        res.write(`data: ${JSON.stringify({
          status: 'error',
          message: error.message || 'Analysis failed'
        })}\n\n`);
        res.end();
      });

    // Note: Connection handling moved above to track connectionAlive flag

  } catch (error: any) {
    console.error('[API] Stream setup error:', error);
    if (!res.headersSent) {
      res.setHeader('Content-Type', 'text/event-stream');
      res.setHeader('Cache-Control', 'no-cache');
      res.setHeader('Connection', 'keep-alive');
      res.setHeader('Access-Control-Allow-Origin', '*');
    }
    res.write(`event: error\n`);
    res.write(`data: ${JSON.stringify({
      status: 'error',
      message: error.message || 'Failed to start analysis'
    })}\n\n`);
    res.end();
  }
});

router.get('/documents', async (req: Request, res: Response) => {
  try {
    const db = await getDb();
    const ticker = typeof req.query.ticker === 'string' ? req.query.ticker : undefined;
    const sourceType = typeof req.query.sourceType === 'string' ? req.query.sourceType : undefined;
    const limit = typeof req.query.limit === 'string' ? parseInt(req.query.limit, 10) : 200;
    const query: any = {};
    if (ticker) query.ticker = ticker.toUpperCase();
    if (sourceType) query.source_type = sourceType;
    const docs = await db.collection('documents').find(query).sort({ updated_at: -1 }).limit(Number.isNaN(limit) ? 200 : limit).toArray();
    const normalized = docs.map((d: any) => ({ ...d, id: String(d._id) }));
    res.json({ status: 'success', documents: normalized });
  } catch (error: any) {
    res.status(500).json({ status: 'error', message: error.message || 'Failed to load documents' });
  }
});

router.get('/documents/:documentId', async (req: Request, res: Response) => {
  try {
    const { documentId } = req.params;
    const db = await getDb();
    const doc = await db.collection('documents').findOne({ _id: documentId } as any);
    if (!doc) {
      return res.status(404).json({ status: 'error', message: 'Document not found' });
    }

    let previewText = '';
    let previewChunks: string[] = [];
    try {
      const preview = await runDocumentPreview(documentId);
      previewText = preview.preview_text || '';
      previewChunks = preview.preview_chunks || [];
    } catch (previewError: any) {
      console.warn('[API] Document preview unavailable:', previewError.message);
    }

    const hasPdf = doc.source_type === 'user_pdf' || Boolean(doc.source_url);
    const fileUrl = doc.gridfs_file_id ? `/api/documents/${encodeURIComponent(documentId)}/pdf` : undefined;

    res.json({
      status: 'success',
      document: {
        ...doc,
        has_pdf: hasPdf,
        has_text_preview: Boolean(previewText),
        file_url: fileUrl,
        preview_text: previewText,
        preview_chunks: previewChunks
      }
    });
  } catch (error: any) {
    res.status(500).json({ status: 'error', message: error.message || 'Failed to load document details' });
  }
});

router.get('/documents/:documentId/pdf', async (req: Request, res: Response) => {
  try {
    const { documentId } = req.params;
    const db = await getDb();
    const doc: any = await db.collection('documents').findOne({ _id: documentId } as any);
    if (!doc || !doc.gridfs_file_id) {
      return res.status(404).json({ status: 'error', message: 'Document file not found' });
    }
    const bucket = new GridFSBucket(db, { bucketName: 'pdfs' });
    res.setHeader('Content-Type', 'application/pdf');
    bucket.openDownloadStream(new ObjectId(doc.gridfs_file_id)).pipe(res);
  } catch (error: any) {
    res.status(404).json({ status: 'error', message: error.message || 'Unable to read document file' });
  }
});

router.get('/analyses/:analysisId/documents', async (req: Request, res: Response) => {
  try {
    const { analysisId } = req.params;
    const db = await getDb();
    const docs = await db.collection('documents').find({ analysis_id: analysisId }).toArray();
    res.json({ status: 'success', documents: docs.map((d: any) => ({ ...d, id: String(d._id) })) });
  } catch (error: any) {
    res.status(500).json({ status: 'error', message: error.message || 'Failed to load analysis documents' });
  }
});

router.get('/analyses', async (req: Request, res: Response) => {
  try {
    const db = await getDb();
    const ticker = typeof req.query.ticker === 'string' ? req.query.ticker.toUpperCase() : undefined;
    const limit = typeof req.query.limit === 'string' ? parseInt(req.query.limit, 10) : 20;
    const skip = typeof req.query.skip === 'string' ? parseInt(req.query.skip, 10) : 0;
    const query: any = {};
    if (ticker) query.ticker = ticker;
    const analyses = await db.collection('analyses')
      .find(query, { projection: { memoMarkdown: 0 } })
      .sort({ createdAt: -1 })
      .skip(skip)
      .limit(limit)
      .toArray();
    res.json({ status: 'success', analyses });
  } catch (error: any) {
    res.status(500).json({ status: 'error', message: error.message || 'Failed to load analyses' });
  }
});

router.get('/analyses/:id', async (req: Request, res: Response) => {
  try {
    const db = await getDb();
    const analysis = await db.collection('analyses').findOne({ _id: req.params.id } as any);
    if (!analysis) return res.status(404).json({ status: 'error', message: 'Analysis not found' });
    res.json({ status: 'success', analysis });
  } catch (error: any) {
    res.status(500).json({ status: 'error', message: error.message || 'Failed to load analysis' });
  }
});

router.delete('/analyses/:id', async (req: Request, res: Response) => {
  try {
    const db = await getDb();
    const analysisId = req.params.id;
    await db.collection('analyses').deleteOne({ _id: analysisId } as any);
    await db.collection('telemetry').deleteMany({ analysis_id: analysisId });
    res.json({ status: 'success' });
  } catch (error: any) {
    res.status(500).json({ status: 'error', message: error.message || 'Failed to delete analysis' });
  }
});

export default router;

