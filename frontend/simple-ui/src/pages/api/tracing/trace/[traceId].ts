// Next.js API route to proxy Jaeger single trace endpoint

import type { NextApiRequest, NextApiResponse } from 'next';
import axios from 'axios';

// Use jaeger hostname for Docker, localhost for local dev
// In Docker: http://jaeger:16686
// Local dev: http://localhost:16686
const JAEGER_URL = process.env.JAEGER_URL || process.env.NEXT_PUBLIC_JAEGER_URL || 'http://jaeger:16686';

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse
) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { traceId } = req.query;
  
  if (!traceId || typeof traceId !== 'string') {
    return res.status(400).json({ error: 'Trace ID is required' });
  }

  try {

    const url = `${JAEGER_URL}/api/traces/${traceId}`;
    console.log(`[API] Fetching trace from: ${url}`);
    
    const response = await axios.get(url, {
      timeout: 10000, // 10 second timeout
    });
    
    console.log(`[API] Trace fetched successfully, spans: ${response.data?.data?.[0]?.spans?.length || 0}`);
    res.status(200).json(response.data);
  } catch (error: any) {
    console.error('Error proxying Jaeger trace:', error);
    console.error('Error details:', {
      message: error.message,
      code: error.code,
      response: error.response?.data,
      status: error.response?.status,
      url: error.config?.url,
    });
    
    // Provide more helpful error messages
    let errorMessage = error.message;
    let statusCode = 500;
    
    if (error.code === 'ECONNREFUSED' || error.code === 'ENOTFOUND') {
      errorMessage = `Cannot connect to Jaeger at ${JAEGER_URL}. Make sure Jaeger is running.`;
      statusCode = 503; // Service Unavailable
    } else if (error.response?.status === 404) {
      errorMessage = `Trace not found: ${traceId}`;
      statusCode = 404;
    } else if (error.response?.status) {
      statusCode = error.response.status;
      errorMessage = error.response.data?.message || error.message;
    }
    
    res.status(statusCode).json({ 
      error: 'Failed to fetch trace',
      message: errorMessage,
      details: error.response?.data || error.code,
      jaegerUrl: JAEGER_URL,
      traceId: traceId,
    });
  }
}

