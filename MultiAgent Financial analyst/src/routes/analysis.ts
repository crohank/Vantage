/**
 * Analysis Routes
 * Handles stock analysis requests
 */

import express, { Request, Response } from 'express';
import { runAnalysis, ProgressData, AnalysisResult } from '../services/pythonService.js'; // Keep .js extension for ESM compatibility

const router = express.Router();

interface AnalyzeRequest {
  ticker: string;
  horizon: string;
  risk_profile: string;
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

/**
 * POST /api/analyze
 * Standard analysis endpoint (returns results after completion)
 */
router.post('/analyze', async (req: Request<{}, SuccessResponse | ErrorResponse, AnalyzeRequest>, res: Response<SuccessResponse | ErrorResponse>) => {
  try {
    const { ticker, horizon, risk_profile } = req.body;

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
    const result = await runAnalysis(
      ticker.toUpperCase(),
      horizon.toLowerCase(),
      risk_profile.toLowerCase()
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
  }
});

/**
 * POST /api/analyze/stream
 * Streaming analysis endpoint with Server-Sent Events (SSE)
 * Provides real-time progress updates
 */
router.post('/analyze/stream', async (req: Request<{}, void, AnalyzeRequest>, res: Response) => {
  try {
    const { ticker, horizon, risk_profile } = req.body;

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
    res.on('error', (error) => {
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
      sendProgress
    )
      .then((result: AnalysisResult) => {
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

export default router;

