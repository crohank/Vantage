/**
 * Python Service
 * Executes Python analysis script and captures output in real-time
 */

import { spawn, ChildProcess } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';
import { readFileSync, existsSync } from 'fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export interface ProgressData {
  step: string;
  message: string;
  timestamp: number;
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
  progressMessages?: ProgressData[];
  parseError?: string;
}

/**
 * Run Python analysis with real-time output capture
 */
export function runAnalysis(
  ticker: string,
  horizon: string,
  riskProfile: string,
  onProgress: ((data: ProgressData) => void) | null = null
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
    
    // Try to use venv Python if it exists, otherwise use system Python
    // On Render/production, venv won't exist, so use system Python
    let pythonExecutable = 'python3'; // Default to python3 (Render uses this)
    
    // Check for venv in project root (go up from MultiAgent Financial analyst to analyst root)
    const analystRoot = path.resolve(projectRoot, '..');
    
    // Try python3 first (Linux/Mac/Render)
    if (!existsSync(path.join(analystRoot, 'venv'))) {
      // No venv, use system Python
      // Try python3 first, then python as fallback
      pythonExecutable = process.platform === 'win32' ? 'python' : 'python3';
    } else {
      // Local development with venv
      const venvPython = process.platform === 'win32' 
        ? path.join(analystRoot, 'venv', 'Scripts', 'python.exe')
        : path.join(analystRoot, 'venv', 'bin', 'python');
      pythonExecutable = existsSync(venvPython) ? venvPython : (process.platform === 'win32' ? 'python' : 'python3');
    }
    
    console.log('[PythonService] Project root:', projectRoot);
    console.log('[PythonService] Python script:', pythonScript);
    console.log('[PythonService] Using Python:', pythonExecutable);
    console.log('[PythonService] Platform:', process.platform);
    
    // Spawn Python process with unbuffered output (-u flag) and JSON_OUTPUT flag
    const pythonProcess: ChildProcess = spawn(pythonExecutable, [
      '-u', // Unbuffered output - important for real-time streaming
      pythonScript,
      ticker,
      horizon,
      riskProfile
    ], {
      cwd: projectRoot, // Set working directory to project root (where Python files are)
      shell: process.platform === 'win32', // Use shell only on Windows
      env: {
        ...process.env,
        JSON_OUTPUT: 'true', // Tell Python to output JSON
        PYTHONUNBUFFERED: '1' // Also set environment variable for unbuffered output
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
          
          // Try to read memo file if path is mentioned in output
          const memoPath = extractMemoPath(stdout);
          if (memoPath && existsSync(memoPath)) {
            try {
              result.memo = readFileSync(memoPath, 'utf-8');
            } catch (readError) {
              console.error('[PythonService] Error reading memo file:', readError);
            }
          }
          
          result.progressMessages = progressMessages;
          resolve(result);
        } else {
          // Fallback: Look for any JSON object in stdout
          const jsonMatch = stdout.match(/\{[\s\S]*\}/);
          if (jsonMatch) {
            const result: AnalysisResult = JSON.parse(jsonMatch[0]);
            
            // Try to read memo file
            const memoPath = extractMemoPath(stdout);
            if (memoPath && existsSync(memoPath)) {
              try {
                result.memo = readFileSync(memoPath, 'utf-8');
              } catch (readError) {
                console.error('[PythonService] Error reading memo file:', readError);
              }
            }
            
            result.progressMessages = progressMessages;
            resolve(result);
          } else {
            // Parse text output to extract key information
            const result = parseTextOutput(stdout);
            
            // Try to read memo file
            const memoPath = extractMemoPath(stdout);
            if (memoPath && existsSync(memoPath)) {
              try {
                result.memo = readFileSync(memoPath, 'utf-8');
              } catch (readError) {
                console.error('[PythonService] Error reading memo file:', readError);
              }
            }
            
            result.progressMessages = progressMessages;
            resolve(result);
          }
        }
      } catch (parseError: any) {
        console.error('[PythonService] JSON parse error:', parseError);
        // If parsing fails, return parsed text output
        const result = parseTextOutput(stdout);
        
        // Try to read memo file
        const memoPath = extractMemoPath(stdout);
        if (memoPath && existsSync(memoPath)) {
          try {
            result.memo = readFileSync(memoPath, 'utf-8');
          } catch (readError) {
            console.error('[PythonService] Error reading memo file:', readError);
          }
        }
        
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

function extractMemoPath(output: string): string | null {
  // Look for "Investment memo saved to: outputs/TICKER_memo.md"
  const memoMatch = output.match(/Investment memo saved to:\s*(outputs[\/\\][^\s\n]+)/i);
  if (memoMatch) {
    const relativePath = memoMatch[1].replace(/\//g, path.sep); // Normalize path separators
    // Resolve relative to project root (four levels up from services)
    const projectRoot = path.resolve(__dirname, '../../../..');
    return path.join(projectRoot, relativePath);
  }
  return null;
}

