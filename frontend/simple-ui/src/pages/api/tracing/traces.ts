// Next.js API route to proxy Jaeger traces endpoint

import type { NextApiRequest, NextApiResponse } from 'next';
import axios from 'axios';

// JAEGER_URL must be set in environment variables
// Local: http://localhost:16686
// Deployed: https://demo-orchestrate.ai4inclusion.org/jaeger
const JAEGER_URL = process.env.JAEGER_URL;

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse
) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  if (!JAEGER_URL) {
    return res.status(500).json({ 
      error: 'Configuration error',
      message: 'JAEGER_URL environment variable is not set. Please configure it in your environment.'
    });
  }

  try {
    const { service, operation, limit, lookback, minDuration, maxDuration, start, end, tags } = req.query;
    
    const params = new URLSearchParams();
    if (service) params.append('service', service as string);
    if (operation) params.append('operation', operation as string);
    if (limit) params.append('limit', limit as string);
    if (lookback) params.append('lookback', lookback as string);
    if (minDuration) params.append('minDuration', minDuration as string);
    if (maxDuration) params.append('maxDuration', maxDuration as string);
    if (start) params.append('start', start as string);
    if (end) params.append('end', end as string);
    if (tags) params.append('tags', tags as string);

    const url = `${JAEGER_URL}/api/traces?${params.toString()}`;
    const response = await axios.get(url);
    res.status(200).json(response.data);
  } catch (error: any) {
    console.error('Error proxying Jaeger traces:', error);
    res.status(500).json({ 
      error: 'Failed to fetch traces',
      message: error.message 
    });
  }
}

