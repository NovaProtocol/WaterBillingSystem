# Error Codes Reference

Customer-facing errors display a code like `ERR0001` rather than the technical error detail. Frontend error text comes from the canonical `{error:{code,message,request_id}}` envelope message plus code, so a raw `[object Object]` in the UI means a renderer read the envelope object as text. Support staff can use this reference to diagnose the issue.

## Customer Portal (ERR1xxx)

| Code | Meaning | Action |
|------|---------|--------|
| `ERR0001` | Generic verification failure | Check customer-portal and API logs for details |
| `CUS500` | Backend login succeeded without a customer number | Check API login response contract and customer-portal logs |
| `CUS501` | Session token creation failed after verification | Check portal `SECRET_KEY` length and signing logs |

## API Internal Endpoints (CUSxxx)

| Code | Meaning | Action |
|------|---------|--------|
| `CUS400` | API request missing required field (account_number) | This is a bug in the calling code — check customer-portal logs |
| `CUS404` | Customer number not found in database | Verify the customer number is correct. Customer may be inactive or not yet enrolled |
| `CUS403` | Registered name doesn't match database record | Customer may be using a different name than what's on file. Verify spelling |

## Staff Portal — API Client Errors

Staff portal errors surface from `api_client.py` calls. The underlying HTTP status code determines the issue:

| HTTP Status | Meaning | Action |
|-------------|---------|--------|
| 401 | Internal API key mismatch | Check `INTERNAL_API_KEY` env var matches between containers |
| 403 | Staff lacks required permission flag | Check staff account permissions in the dashboard |
| 404 | Resource not found | The requested record was deleted or doesn't exist |
| 409 | Conflict (duplicate entry) | The record already exists |

## How Error Codes Work

1. When an error occurs, the server logs the full error message with the error code prefix
2. The customer sees only the error code
3. Support staff look up the code in this reference
4. If the code doesn't exist in this reference, check Docker logs for the full error message:
   ```
   docker logs waterbillingsystem_customerportal | grep ERR
   ```
