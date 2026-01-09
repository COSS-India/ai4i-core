// Next.js API route to proxy Jaeger services endpoint

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
    const response = await axios.get(`${JAEGER_URL}/api/services`);
    res.status(200).json(response.data);
  } catch (error: any) {
    console.error('Error proxying Jaeger services:', error);
    res.status(500).json({ 
      error: 'Failed to fetch services',
      message: error.message 
    });
  }
}

