import { parseApiError } from '../../src/utils/errorHandling/parseError';
import { AxiosError } from 'axios';

describe('parseApiError', () => {
  it('extracts a simple message field', () => {
    const error = {
      response: { status: 400, data: { message: 'Something failed' } },
    };
    expect(parseApiError(error)).toMatchObject({
      title: 'Validation Error',
      message: 'Something failed',
      statusCode: 400,
      type: 'error',
    });
  });

  it('extracts error field', () => {
    const error = {
      response: { status: 401, data: { error: 'Invalid API Key' } },
    };
    expect(parseApiError(error).message).toBe('Invalid API Key');
  });

  it('extracts detail string', () => {
    const error = {
      response: { status: 401, data: { detail: 'Unauthorized' } },
    };
    expect(parseApiError(error).message).toBe('Unauthorized');
  });

  it('extracts errors array of objects', () => {
    const error = {
      response: {
        status: 400,
        data: { errors: [{ message: 'Email already exists' }] },
      },
    };
    expect(parseApiError(error).message).toBe('Email already exists');
  });

  it('extracts errors array of strings', () => {
    const error = {
      response: {
        status: 422,
        data: {
          errors: ['Name is required', 'Email is invalid'],
        },
      },
    };
    expect(parseApiError(error).message).toBe('Name is required; Email is invalid');
  });

  it('extracts nested data.message', () => {
    const error = {
      response: {
        status: 409,
        data: { data: { message: 'Duplicate entry' } },
      },
    };
    expect(parseApiError(error).message).toBe('Duplicate entry');
  });

  it('extracts message array', () => {
    const error = {
      response: {
        status: 400,
        data: {
          statusCode: 400,
          message: ['Field A is required', 'Field B is invalid'],
        },
      },
    };
    expect(parseApiError(error).message).toBe('Field A is required; Field B is invalid');
  });

  it('handles plain text response body', () => {
    const error = {
      response: { status: 500, data: 'Internal Server Error' },
    };
    expect(parseApiError(error).message).toBe('Internal Server Error');
  });

  it('never throws on null/undefined', () => {
    expect(() => parseApiError(null)).not.toThrow();
    expect(() => parseApiError(undefined)).not.toThrow();
    expect(parseApiError(null).message).toBeTruthy();
  });

  it('maps axios errors', () => {
    const axiosError = new AxiosError(
      'Request failed',
      'ERR_BAD_REQUEST',
      undefined,
      undefined,
      {
        status: 404,
        statusText: 'Not Found',
        headers: {},
        config: {} as never,
        data: { message: 'Resource missing' },
      }
    );
    expect(parseApiError(axiosError)).toMatchObject({
      title: 'Not Found',
      message: 'Resource missing',
      statusCode: 404,
    });
  });

  it('preserves backend message exactly', () => {
    const error = {
      response: { status: 409, data: { message: 'API Key already exists.' } },
    };
    expect(parseApiError(error).message).toBe('API Key already exists.');
  });

  it('includes endpoint validation failure details', () => {
    const error = {
      response: {
        status: 400,
        data: {
          detail: {
            code: 'ENDPOINT_VALIDATION_ERROR',
            message: 'Service endpoint validation failed.',
            details: 'Request timed out after 15.0s: https://example.com/infer',
          },
        },
      },
    };

    expect(parseApiError(error).message).toBe(
      'Service endpoint validation failed. Request timed out after 15.0s: https://example.com/infer'
    );
  });
});
