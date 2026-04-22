/**
 * Python Service
 * Executes Python analysis script and captures output in real-time
 */

import { spawn, ChildProcess } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';
import { existsSync } from 'fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export interface ProgressData {
  step: string;
  message: string;
  timestamp: number;
}

export interface TelemetrySummary {
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  total_cost_usd?: number;
  total_latency_ms?: number;
  num_calls?: number;
}

export interface AnalysisResult {
  recommendation: string;
  confidence_score: number;
  scenarios: Record<string, { return: number; prob: number }>;
  memo: string;
  market_data?: Record<string, any>;
  macro_data?: Record<string, any>;
  risk_analysis?: Record<string, any>;
  timing?: Record<string, number>;
  telemetry?: TelemetrySummary;
  document_sources?: Array<Record<string, any>>;
  progressMessages?: ProgressData[];
  parseError?: string;
}

export interface AnalysisOptions {
  uploadedDocumentPath?: string;
  uploadedDocumentName?: string;
}

/**
 * Run Python analysis with real-time output capture
 */
export function runAnalysis(
  ticker: string,
  horizon: string,
  riskProfile: string,
  onProgress: ((data: ProgressData) => void) | null = null,
  options: AnalysisOptions = {}
): Promise<AnalysisResult> {
  return new Promise((resolve, reject) => {
    // Path to main.py
    // __dirname = MultiAgent Financial analyst/dist/services (after build)
    // ../.. = MultiAgent Financial analyst/ (project root where Python files are)
    const projectRoot = path.resolve(__dirname, '../..');
    const pythonScript = path.resolve(projectRoot, 'main.py');
    
    console.log('[PythonService] Project root:', projectRoot);
    console.log('[PythonService] Python script:', pythonScript);
    console.log('[PythonService] Script exists:', existsSync(pythonScript));
    
    if (!existsSync(pythonScript)) {
      reject(new Error(`Python script not found at: ${pythonScript}`));
      return;
    }
    
    // In Docker, always use system Python
    // Check if we're in Docker (common indicators)
    const isDocker = process.env.DOCKER_CONTAINER === 'true' || 
                     existsSync('/.dockerenv') ||
                     (process.env.NODE_ENV === 'production' && !existsSync(path.resolve(projectRoot, '..', 'venv')));
    
    // Use python3 in Docker/Linux, python on Windows (for local dev)
    let pythonExecutable: string;
    if (isDocker) {
      pythonExecutable = 'python3';
    } else {
      // Local development: try venv first, then system Python
      const analystRoot = path.resolve(projectRoot, '..');
      const venvPath = process.platform === 'win32' 
        ? path.join(analystRoot, 'venv', 'Scripts', 'python.exe')
        : path.join(analystRoot, 'venv', 'bin', 'python');
      
      if (existsSync(venvPath)) {
        pythonExecutable = venvPath;
      } else {
        pythonExecutable = process.platform === 'win32' ? 'python' : 'python3';
      }
    }
    
    console.log('[PythonService] Project root:', projectRoot);
    console.log('[PythonService] Python script:', pythonScript);
    console.log('[PythonService] Using Python:', pythonExecutable);
    console.log('[PythonService] Platform:', process.platform);
    
    // On Windows, use relative path from cwd to avoid issues with spaces in absolute paths
    // Since cwd is set to projectRoot, we can just use 'main.py'
    const scriptPath = 'main.py';
    
    // Ensure Python executable path is properly quoted if it contains spaces
    // spawn handles this automatically when shell=false, but we'll use the path as-is
    
    // Spawn Python process with unbuffered output (-u flag) and JSON_OUTPUT flag
    const pythonArgs = [
      '-u', // Unbuffered output - important for real-time streaming
      scriptPath, // Use relative path from cwd
      ticker,
      horizon,
      riskProfile
    ];
    if (options.uploadedDocumentPath) {
      pythonArgs.push(options.uploadedDocumentPath);
    }
    
    console.log('[PythonService] Python args:', pythonArgs);
    console.log('[PythonService] Working directory:', projectRoot);
    
    const pythonProcess: ChildProcess = spawn(pythonExecutable, pythonArgs, {
      cwd: projectRoot, // Set working directory to project root (where Python files are)
      shell: false, // Don't use shell - spawn handles arguments correctly when shell=false
      env: {
        ...process.env,
        JSON_OUTPUT: 'true', // Tell Python to output JSON
        PYTHONUNBUFFERED: '1', // Also set environment variable for unbuffered output
        UPLOADED_DOC_PATH: options.uploadedDocumentPath || '',
        UPLOADED_DOC_NAME: options.uploadedDocumentName || ''
      }
    });

    let stdout = '';
    let stderr = '';
    const progressMessages: ProgressData[] = [];
    let processStarted = false;

    // Send immediate message that Python process is starting
    if (onProgress) {
      onProgress({
        step: 'system',
        message: 'Python process started, initializing...',
        timestamp: Date.now()
      });
    }

    // Capture stdout line by line (real-time)
    pythonProcess.stdout?.on('data', (data: Buffer) => {
      if (!processStarted) {
        processStarted = true;
        console.log('[PythonService] First output received from Python process');
        if (onProgress) {
          onProgress({
            step: 'system',
            message: 'Python process is running and producing output...',
            timestamp: Date.now()
          });
        }
      }
      
      const chunk = data.toString();
      console.log('[PythonService] Received chunk from Python:', chunk.substring(0, 100).replace(/\n/g, '\\n'));
      stdout += chunk;
      
      // Split by newlines and process each line
      const lines = chunk.split('\n').filter((line: string) => line.trim());
      
      for (const line of lines) {
        // Call progress callback if provided
        if (onProgress) {
          // Parse step from message (e.g., "[Market Data Agent] ...")
          const stepMatch = line.match(/\[([^\]]+)\]/);
          const step = stepMatch ? stepMatch[1] : 'system';
          
          const progressData: ProgressData = {
            step,
            message: line.trim(),
            timestamp: Date.now()
          };
          
          onProgress(progressData);
          progressMessages.push(progressData);
        } else {
          const stepMatch = line.match(/\[([^\]]+)\]/);
          progressMessages.push({
            step: stepMatch ? stepMatch[1] : 'system',
            message: line.trim(),
            timestamp: Date.now()
          });
        }
      }
    });

    // Capture stderr
    pythonProcess.stderr?.on('data', (data: Buffer) => {
      const chunk = data.toString();
      stderr += chunk;
      const trimmedChunk = chunk.trim();
      
      // Only log non-empty stderr
      if (trimmedChunk) {
        console.error('[PythonService] stderr:', trimmedChunk);
        
        if (onProgress) {
          const progressData: ProgressData = {
            step: 'error',
            message: `Error: ${trimmedChunk}`,
            timestamp: Date.now()
          };
          onProgress(progressData);
          progressMessages.push(progressData);
        }
      }
    });

    // Log when process starts
    console.log('[PythonService] Python process spawned, waiting for output...');
    
    // Handle process completion
    pythonProcess.on('close', (code: number | null) => {
      console.log(`[PythonService] Python process exited with code: ${code}`);
      console.log(`[PythonService] Total stdout length: ${stdout.length} chars`);
      console.log(`[PythonService] Total stderr length: ${stderr.length} chars`);
      if (code !== 0) {
        const stdoutPreview = stdout.substring(0, 1000);
        const stderrPreview = stderr.substring(0, 1000);
        console.error('[PythonService] Process failed. stdout preview:', stdoutPreview);
        console.error('[PythonService] Process failed. stderr preview:', stderrPreview);
        
        // Try to extract meaningful error message
        let errorMessage = `Python process exited with code ${code}`;
        if (stderr) {
          // Try to get the last meaningful error line
          const stderrLines = stderr.split('\n').filter(line => line.trim());
          const lastErrorLine = stderrLines[stderrLines.length - 1];
          if (lastErrorLine && !lastErrorLine.includes('Traceback')) {
            errorMessage = lastErrorLine;
          } else if (stderrLines.length > 0) {
            errorMessage = stderrLines.join('; ');
          }
        } else if (stdout) {
          // Sometimes errors are in stdout
          const stdoutLines = stdout.split('\n').filter(line => 
            line.trim() && (
              line.toLowerCase().includes('error') || 
              line.toLowerCase().includes('exception') ||
              line.toLowerCase().includes('failed')
            )
          );
          if (stdoutLines.length > 0) {
            errorMessage = stdoutLines[stdoutLines.length - 1];
          }
        }
        
        const error = new Error(errorMessage);
        (error as any).code = code;
        (error as any).stdout = stdout;
        (error as any).stderr = stderr;
        reject(error);
        return;
      }

      // Try to parse JSON from stdout
      try {
        // Look for JSON between markers (===JSON_OUTPUT_START=== and ===JSON_OUTPUT_END===)
        const jsonStart = stdout.indexOf('===JSON_OUTPUT_START===');
        const jsonEnd = stdout.indexOf('===JSON_OUTPUT_END===');
        
        if (jsonStart !== -1 && jsonEnd !== -1) {
          const jsonStr = stdout.substring(jsonStart + 24, jsonEnd).trim();
          const result: AnalysisResult = JSON.parse(jsonStr);
          
          result.progressMessages = progressMessages;
          resolve(result);
        } else {
          // Fallback: Look for any JSON object in stdout
          const jsonMatch = stdout.match(/\{[\s\S]*\}/);
          if (jsonMatch) {
            const result: AnalysisResult = JSON.parse(jsonMatch[0]);
            
            result.progressMessages = progressMessages;
            resolve(result);
          } else {
            // Parse text output to extract key information
            const result = parseTextOutput(stdout);
            
            result.progressMessages = progressMessages;
            resolve(result);
          }
        }
      } catch (parseError: any) {
        console.error('[PythonService] JSON parse error:', parseError);
        // If parsing fails, return parsed text output
        const result = parseTextOutput(stdout);
        
        result.progressMessages = progressMessages;
        result.parseError = parseError.message;
        resolve(result);
      }
    });

    // Handle process errors (e.g., Python executable not found)
    pythonProcess.on('error', (error: Error) => {
      console.error('[PythonService] Failed to start Python process:', error);
      reject(new Error(`Failed to start Python process: ${error.message}. Make sure Python is installed and accessible.`));
    });

    // Set timeout (60 minutes) - analysis can take 30+ minutes with LLM warmup and calls
    // Warmup alone can take 25+ minutes on first run
    const timeout = setTimeout(() => {
      pythonProcess.kill();
      reject(new Error('Analysis timeout: Process took longer than 60 minutes'));
    }, 60 * 60 * 1000);

    pythonProcess.on('close', () => {
      clearTimeout(timeout);
    });
  });
}

/**
 * Resolve a natural language query to a stock ticker
 * Spawns: python resolve_query.py "<query>"
 */
export interface QueryResolution {
  ticker: string | null;
  horizon?: string | null;
  risk_profile?: string | null;
  original_query: string;
  resolved: boolean;
  confidence: number;
  error?: string | null;
}

export interface DocumentPreviewResult {
  document_id: string;
  filename?: string;
  preview_chunks: string[];
  preview_text: string;
}

export function runQueryResolution(query: string): Promise<QueryResolution> {
  return new Promise((resolve, reject) => {
    const projectRoot = path.resolve(__dirname, '../..');
    const pythonScript = path.resolve(projectRoot, 'resolve_query.py');

    if (!existsSync(pythonScript)) {
      reject(new Error(`Query resolver script not found at: ${pythonScript}`));
      return;
    }

    // Resolve Python executable (same logic as runAnalysis)
    const isDocker = process.env.DOCKER_CONTAINER === 'true' ||
                     existsSync('/.dockerenv') ||
                     (process.env.NODE_ENV === 'production' && !existsSync(path.resolve(projectRoot, '..', 'venv')));

    let pythonExecutable: string;
    if (isDocker) {
      pythonExecutable = 'python3';
    } else {
      const analystRoot = path.resolve(projectRoot, '..');
      const venvPath = process.platform === 'win32'
        ? path.join(analystRoot, 'venv', 'Scripts', 'python.exe')
        : path.join(analystRoot, 'venv', 'bin', 'python');

      if (existsSync(venvPath)) {
        pythonExecutable = venvPath;
      } else {
        pythonExecutable = process.platform === 'win32' ? 'python' : 'python3';
      }
    }

    console.log(`[PythonService] Resolving query: "${query}"`);

    const pythonProcess = spawn(pythonExecutable, ['-u', 'resolve_query.py', query], {
      cwd: projectRoot,
      shell: false,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: '1'
      }
    });

    let stdout = '';
    let stderr = '';

    pythonProcess.stdout?.on('data', (data: Buffer) => {
      stdout += data.toString();
    });

    pythonProcess.stderr?.on('data', (data: Buffer) => {
      stderr += data.toString();
    });

    pythonProcess.on('close', (code: number | null) => {
      if (code !== 0) {
        console.error('[PythonService] Query resolution failed:', stderr);
        reject(new Error(`Query resolution failed: ${stderr || `exit code ${code}`}`));
        return;
      }

      try {
        const result: QueryResolution = JSON.parse(stdout.trim());
        console.log(`[PythonService] Query resolved: "${query}" → ${result.ticker || 'null'} (confidence: ${result.confidence})`);
        resolve(result);
      } catch (parseError: any) {
        console.error('[PythonService] Failed to parse query resolution:', stdout);
        reject(new Error(`Failed to parse query resolution: ${parseError.message}`));
      }
    });

    pythonProcess.on('error', (error: Error) => {
      reject(new Error(`Failed to start query resolver: ${error.message}`));
    });

    // 30 second timeout for query resolution
    const timeout = setTimeout(() => {
      pythonProcess.kill();
      reject(new Error('Query resolution timed out (30s)'));
    }, 30000);

    pythonProcess.on('close', () => clearTimeout(timeout));
  });
}

export function runDocumentPreview(documentId: string): Promise<DocumentPreviewResult> {
  return new Promise((resolve, reject) => {
    const projectRoot = path.resolve(__dirname, '../..');
    const pythonScript = path.resolve(projectRoot, 'get_document_preview.py');

    if (!existsSync(pythonScript)) {
      reject(new Error(`Document preview script not found at: ${pythonScript}`));
      return;
    }

    const isDocker = process.env.DOCKER_CONTAINER === 'true' ||
                     existsSync('/.dockerenv') ||
                     (process.env.NODE_ENV === 'production' && !existsSync(path.resolve(projectRoot, '..', 'venv')));

    let pythonExecutable: string;
    if (isDocker) {
      pythonExecutable = 'python3';
    } else {
      const analystRoot = path.resolve(projectRoot, '..');
      const venvPath = process.platform === 'win32'
        ? path.join(analystRoot, 'venv', 'Scripts', 'python.exe')
        : path.join(analystRoot, 'venv', 'bin', 'python');
      pythonExecutable = existsSync(venvPath)
        ? venvPath
        : (process.platform === 'win32' ? 'python' : 'python3');
    }

    const pythonProcess = spawn(pythonExecutable, ['-u', 'get_document_preview.py', documentId], {
      cwd: projectRoot,
      shell: false,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: '1'
      }
    });

    let stdout = '';
    let stderr = '';

    pythonProcess.stdout?.on('data', (data: Buffer) => {
      stdout += data.toString();
    });
    pythonProcess.stderr?.on('data', (data: Buffer) => {
      stderr += data.toString();
    });

    pythonProcess.on('close', (code: number | null) => {
      if (code !== 0) {
        reject(new Error(`Document preview failed: ${stderr || stdout || `exit code ${code}`}`));
        return;
      }
      try {
        const trimmed = stdout.trim();
        const jsonLine = trimmed
          .split(/\r?\n/)
          .map((line) => line.trim())
          .reverse()
          .find((line) => line.startsWith('{') && line.endsWith('}'));
        const payload = jsonLine || trimmed;
        const parsed = JSON.parse(payload) as DocumentPreviewResult;
        resolve({
          document_id: parsed.document_id,
          filename: parsed.filename,
          preview_chunks: parsed.preview_chunks || [],
          preview_text: parsed.preview_text || ''
        });
      } catch (error: any) {
        reject(new Error(`Failed to parse document preview response: ${error.message}`));
      }
    });

    pythonProcess.on('error', (error: Error) => {
      reject(new Error(`Failed to start document preview script: ${error.message}`));
    });
  });
}

/**
 * Parse text output from Python script
 * Extracts key information from CLI output
 */
function parseTextOutput(output: string): AnalysisResult {
  const result: AnalysisResult = {
    recommendation: extractValue(output, /Recommendation:\s*(\w+)/i) || '',
    confidence_score: parseFloat(extractValue(output, /Confidence Score:\s*([\d.]+)/i) || '0') || 0,
    scenarios: {},
    memo: '',
    progressMessages: []
  };

  // Extract scenarios
  const scenarioMatch = output.match(/Scenarios:([\s\S]*?)(?=\nInvestment memo|$)/i);
  if (scenarioMatch) {
    const scenariosText = scenarioMatch[1];
    ['bull', 'base', 'bear'].forEach(scenario => {
      const regex = new RegExp(`${scenario}[^:]*:\\s*([+-]?[\\d.]+)%[^,]*,\\s*(\\d+)%`, 'i');
      const match = scenariosText.match(regex);
      if (match) {
        result.scenarios[scenario] = {
          return: parseFloat(match[1]) / 100,
          prob: parseFloat(match[2]) / 100
        };
      }
    });
  }

  return result;
}

function extractValue(text: string, regex: RegExp): string | null {
  const match = text.match(regex);
  return match ? match[1].trim() : null;
}

// Memo content is now returned directly in JSON output.

