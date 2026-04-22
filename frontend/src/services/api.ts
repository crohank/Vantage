/**
 * API Service
 * Handles communication with the backend API
 */

const BASE_URL = import.meta.env.VITE_API_URL || ''
// Normalize API base URL to always end with /api
const API_BASE_URL = BASE_URL.endsWith('/api') ? BASE_URL : `${BASE_URL.replace(/\/$/, '')}/api`

export interface QueryResolution {
  ticker: string | null
  horizon?: string | null
  risk_profile?: string | null
  original_query: string
  resolved: boolean
  confidence: number
  error?: string | null
}

export interface ProgressData {
  step: string
  message: string
  timestamp: number
}

export interface TelemetrySummary {
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
  total_cost_usd?: number
  total_latency_ms?: number
  num_calls?: number
}

export interface AnalysisResults {
  recommendation: string
  confidence_score: number
  scenarios: Record<string, { return: number; prob: number }>
  memo: string
  market_data?: Record<string, any>
  macro_data?: Record<string, any>
  risk_analysis?: Record<string, any>
  document_sources?: DocumentRecord[]
  timing?: Record<string, number>
  telemetry?: TelemetrySummary
}

export interface DocumentRecord {
  id: string
  source_type: 'sec_filing' | 'user_pdf' | string
  ticker: string
  analysis_id: string
  title?: string
  filename?: string
  source_url?: string
  filing_date?: string
  chunks?: number
  status?: string
  updated_at?: string
  file_path?: string
}

export interface AnalysisRecord {
  _id: string
  ticker: string
  horizon: string
  riskProfile: string
  recommendation: string
  confidenceScore: number
  scenarios: Record<string, { return: number; prob: number }>
  memoMarkdown?: string
  marketData?: Record<string, any>
  macroData?: Record<string, any>
  riskAnalysis?: Record<string, any>
  documentsUsed?: DocumentRecord[]
  createdAt?: string
}

export interface DocumentDetail extends DocumentRecord {
  has_pdf?: boolean
  has_text_preview?: boolean
  file_url?: string
  preview_text?: string
  preview_chunks?: string[]
}

interface AnalysisResponse {
  status: 'success' | 'error'
  data?: AnalysisResults
  message?: string
  timing?: Record<string, number>
}

/**
 * Analyze stock with progress streaming using Server-Sent Events
 */
export function analyzeStockWithProgress(
  ticker: string,
  horizon: string,
  riskProfile: string,
  documentFile: File | null,
  onProgress: (data: ProgressData) => void,
  onComplete: (data: AnalysisResponse) => void,
  onError: (error: Error) => void
): { abort: () => void } {
  // Use fetch with streaming for POST request
  // Note: EventSource only supports GET, so we use fetch with ReadableStream
  
  const controller = new AbortController()
  let currentEvent: string | null = null
  
  console.log('[Frontend] Starting SSE connection to:', `${API_BASE_URL}/analyze/stream`)
  
  const hasDocument = Boolean(documentFile)
  const requestOptions: RequestInit = {
    method: 'POST',
    headers: {
      'Accept': 'text/event-stream'
    },
    signal: controller.signal
  }

  if (hasDocument && documentFile) {
    const formData = new FormData()
    formData.append('ticker', ticker)
    formData.append('horizon', horizon)
    formData.append('risk_profile', riskProfile)
    formData.append('document', documentFile)
    requestOptions.body = formData
  } else {
    requestOptions.headers = {
      ...requestOptions.headers,
      'Content-Type': 'application/json'
    }
    requestOptions.body = JSON.stringify({
      ticker,
      horizon,
      risk_profile: riskProfile
    })
  }

  fetch(`${API_BASE_URL}/analyze/stream`, requestOptions)
    .then(async (response) => {
      console.log('[Frontend] Response status:', response.status, response.statusText)
      console.log('[Frontend] Response headers:', Object.fromEntries(response.headers.entries()))
      
      if (!response.ok) {
        // Try to get error message from response
        let errorMessage = `HTTP error! status: ${response.status}`
        try {
          const errorData = await response.json() as { message?: string }
          errorMessage = errorData.message || errorMessage
        } catch {
          // If response is not JSON, try to get text
          try {
            const errorText = await response.text()
            if (errorText) errorMessage = errorText
          } catch {
            // Ignore parsing errors
          }
        }
        throw new Error(errorMessage)
      }

      if (!response.body) {
        throw new Error('Response body is not readable')
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let lastDataTime = Date.now()
      let lastKeepAliveTime = Date.now()

      // Set up timeout to detect if connection is stale (no data for 10 minutes)
      // This is longer because LLM warmup and processing can take time
      // Keep-alive messages count as activity, so reset the timer when we receive them
      const connectionTimeout = setInterval(() => {
        const timeSinceLastData = Date.now() - lastDataTime
        const timeSinceLastKeepAlive = Date.now() - lastKeepAliveTime
        
        // If we haven't received ANY data (including keep-alive) for 10 minutes, timeout
        if (timeSinceLastData > 600000 && timeSinceLastKeepAlive > 600000) { // 10 minutes
          console.error('[Frontend] Connection timeout: No data received for 10 minutes')
          reader.cancel()
          clearInterval(connectionTimeout)
          onError(new Error('Connection timeout: No data received for 10 minutes'))
        } else if (timeSinceLastData > 300000 && timeSinceLastKeepAlive < 60000) {
          // If we're getting keep-alives but no real data for 5 minutes, that's OK
          console.log('[Frontend] Waiting for data (keep-alive received recently)')
        }
      }, 30000) // Check every 30 seconds

      try {
        while (true) {
          const { done, value } = await reader.read()
          
          if (done) {
            clearInterval(connectionTimeout)
            console.log('[Frontend] Stream ended (done=true)')
            // Process remaining buffer
            if (buffer.trim()) {
              try {
                processSSELine(buffer.trim(), currentEvent, onProgress, onComplete, onError)
              } catch (e) {
                console.error('[Frontend] Error processing final buffer:', e)
              }
            }
            // If stream ends without completion, it might be an error
            // But don't call onError here - let the backend send an error event if needed
            break
          }

          // Update last data time whenever we receive any data
          lastDataTime = Date.now()
          lastKeepAliveTime = Date.now()
          
          try {
            buffer += decoder.decode(value, { stream: true })
            const lines = buffer.split('\n')
            buffer = lines.pop() || '' // Keep incomplete line in buffer

            for (const line of lines) {
              const trimmed = line.trim()
              // Skip empty lines
              if (!trimmed) continue
              
              // Handle keep-alive comments
              if (trimmed.startsWith(':')) {
                lastKeepAliveTime = Date.now()
                lastDataTime = Date.now() // Keep-alive counts as activity
                // Only log occasionally to reduce noise
                if (Math.random() < 0.1) { // Log ~10% of keep-alives
                  console.log('[Frontend] SSE Keep-alive received')
                }
                continue
              }

              try {
                if (trimmed.startsWith('event: ')) {
                  currentEvent = trimmed.substring(7).trim()
                  console.log('[Frontend] SSE Event type:', currentEvent)
                } else if (trimmed.startsWith('data: ')) {
                  const dataStr = trimmed.substring(6)
                  console.log('[Frontend] SSE Data received:', dataStr.substring(0, 100))
                  processSSELine(dataStr, currentEvent, onProgress, onComplete, onError)
                  currentEvent = null
                } else {
                  // Unknown line format, log for debugging
                  console.warn('[Frontend] Unknown SSE line format:', trimmed.substring(0, 50))
                }
              } catch (lineError: any) {
                console.error('[Frontend] Error processing SSE line:', lineError, 'Line:', trimmed.substring(0, 100))
                // Don't break the stream on a single line error
              }
            }
          } catch (decodeError: any) {
            console.error('[Frontend] Error decoding stream chunk:', decodeError)
            // Continue reading - don't break on decode errors
          }
        }
      } catch (streamError: any) {
        clearInterval(connectionTimeout)
        console.error('[Frontend] Stream reading error:', streamError)
        if (streamError.name === 'AbortError') {
          console.log('[Frontend] Stream aborted by user')
          return
        }
        onError(new Error(`Stream error: ${streamError.message || 'Unknown error'}`))
      }
    })
    .catch((error: Error) => {
      if (error.name === 'AbortError') {
        console.log('[API] Request aborted by user')
        return
      }
      console.error('[API] Analysis error:', error)
      onError(error)
    })

  // Return controller for manual cancellation
  return {
    abort: () => {
      controller.abort()
      console.log('[API] Analysis request aborted by user')
    }
  }
}

export async function fetchDocuments(params?: {
  ticker?: string
  sourceType?: string
  limit?: number
}): Promise<DocumentRecord[]> {
  const query = new URLSearchParams()
  if (params?.ticker) query.set('ticker', params.ticker)
  if (params?.sourceType) query.set('sourceType', params.sourceType)
  if (params?.limit) query.set('limit', String(params.limit))
  const url = `${API_BASE_URL}/documents${query.toString() ? `?${query.toString()}` : ''}`

  const response = await fetch(url)
  if (!response.ok) {
    throw new Error('Failed to load documents')
  }
  const result = await response.json() as { documents?: DocumentRecord[] }
  return result.documents || []
}

export async function fetchAnalysisDocuments(analysisId: string): Promise<DocumentRecord[]> {
  const response = await fetch(`${API_BASE_URL}/analyses/${analysisId}/documents`)
  if (!response.ok) {
    throw new Error('Failed to load analysis documents')
  }
  const result = await response.json() as { documents?: DocumentRecord[] }
  return result.documents || []
}

export async function fetchDocumentById(documentId: string): Promise<DocumentDetail> {
  const response = await fetch(`${API_BASE_URL}/documents/${encodeURIComponent(documentId)}`)
  if (!response.ok) {
    throw new Error('Failed to load document details')
  }
  const result = await response.json() as { document?: DocumentDetail }
  if (!result.document) {
    throw new Error('Document details unavailable')
  }
  return result.document
}

export async function fetchAnalyses(params?: { ticker?: string; limit?: number; skip?: number }): Promise<AnalysisRecord[]> {
  const query = new URLSearchParams()
  if (params?.ticker) query.set('ticker', params.ticker)
  if (params?.limit) query.set('limit', String(params.limit))
  if (params?.skip) query.set('skip', String(params.skip))
  const response = await fetch(`${API_BASE_URL}/analyses${query.toString() ? `?${query.toString()}` : ''}`)
  if (!response.ok) throw new Error('Failed to load analyses')
  const result = await response.json() as { analyses?: AnalysisRecord[] }
  return result.analyses || []
}

export async function fetchAnalysisById(id: string): Promise<AnalysisRecord> {
  const response = await fetch(`${API_BASE_URL}/analyses/${encodeURIComponent(id)}`)
  if (!response.ok) throw new Error('Failed to load analysis')
  const result = await response.json() as { analysis?: AnalysisRecord }
  if (!result.analysis) throw new Error('Analysis not found')
  return result.analysis
}

export async function deleteAnalysis(id: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/analyses/${encodeURIComponent(id)}`, { method: 'DELETE' })
  if (!response.ok) throw new Error('Failed to delete analysis')
}

export function fetchDocumentPdfUrl(id: string): string {
  return `${BASE_URL}/api/documents/${id}/pdf`
}

export function resolveDocumentUrl(pathOrUrl?: string): string | null {
  if (!pathOrUrl) return null
  if (/^https?:\/\//i.test(pathOrUrl)) return pathOrUrl
  const normalizedBase = BASE_URL.replace(/\/$/, '')
  return `${normalizedBase}${pathOrUrl.startsWith('/') ? pathOrUrl : `/${pathOrUrl}`}`
}

function processSSELine(
  dataStr: string,
  eventType: string | null,
  onProgress: (data: ProgressData) => void,
  onComplete: (data: AnalysisResponse) => void,
  onError: (error: Error) => void
) {
  try {
    if (!dataStr || dataStr.trim() === '') {
      console.log('[Frontend] Empty data string, skipping')
      return // Skip empty data
    }

    let data: any
    try {
      data = JSON.parse(dataStr)
    } catch (parseError) {
      console.error('[Frontend] Failed to parse JSON:', parseError, 'Data:', dataStr.substring(0, 200))
      // Try to extract a message if it's not JSON
      if (dataStr.includes('error') || dataStr.includes('Error')) {
        onError(new Error(dataStr))
      }
      return
    }
    
    console.log('[Frontend] Processing SSE data:', { eventType, hasStep: !!data.step, hasMessage: !!data.message, status: data.status })
    
    // Handle based on event type first, then fall back to data structure
    if (eventType === 'error' || data.status === 'error') {
      // Error event - highest priority
      console.error('[Frontend] Error event received:', data)
      onError(new Error(data.message || 'Analysis failed'))
    } else if (eventType === 'complete' || (data.status === 'success' && data.data)) {
      // Complete event
      console.log('[Frontend] Complete event received')
      onComplete(data as AnalysisResponse)
    } else if (eventType === 'progress' || data.step || data.message) {
      // Progress event
      console.log('[Frontend] Progress event received:', data.step, data.message?.substring(0, 50))
      onProgress(data as ProgressData)
    } else {
      // Unknown event type, log for debugging but try to handle as progress
      console.warn('[Frontend] Unknown SSE event type:', eventType, 'Data keys:', Object.keys(data))
      // Try to treat as progress if it has a message
      if (data.message) {
        onProgress(data as ProgressData)
      }
    }
  } catch (e: any) {
    console.error('[Frontend] Error in processSSELine:', e, 'Data:', dataStr.substring(0, 200))
    // Don't throw - just log the error to avoid breaking the stream
    // But if it's a critical error, notify
    if (e.message && e.message.includes('critical')) {
      onError(new Error(`Critical error processing SSE: ${e.message}`))
    }
  }
}

/**
 * Resolve a natural language query to a stock ticker
 */
export async function resolveQuery(query: string): Promise<QueryResolution> {
  const response = await fetch(`${API_BASE_URL}/resolve-query`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ query })
  })

  if (!response.ok) {
    const error = await response.json() as { message?: string }
    throw new Error(error.message || 'Query resolution failed')
  }

  return await response.json() as QueryResolution
}

/**
 * Check if input looks like a direct ticker symbol
 */
export function isLikelyTicker(input: string): boolean {
  return /^[A-Z]{1,5}(-[A-Z]{1,2})?$/.test(input.trim().toUpperCase())
}

/**
 * Standard analyze stock (without progress)
 */
export async function analyzeStock(
  ticker: string,
  horizon: string,
  riskProfile: string
): Promise<AnalysisResults> {
  const response = await fetch(`${API_BASE_URL}/analyze`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      ticker,
      horizon,
      risk_profile: riskProfile
    })
  })

  if (!response.ok) {
    const error = await response.json() as { message?: string }
    throw new Error(error.message || 'Analysis failed')
  }

  const result = await response.json() as AnalysisResponse
  if (result.status === 'error' || !result.data) {
    throw new Error(result.message || 'Analysis failed')
  }

  return result.data
}

