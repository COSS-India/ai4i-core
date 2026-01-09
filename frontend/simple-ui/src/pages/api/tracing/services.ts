// Next.js API route to proxy Jaeger services endpoint

import type { NextApiRequest, NextApiResponse } from 'next';
import axios from 'axios';

const JAEGER_URL = process.env.JAEGER_URL || 'http://jaeger:16686';

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse
) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
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

