# Feasibility Assessment - Product Team Version

This document provides the "Feasibility Assessment" column in non-technical language for the product team.

## Platform Health Metrics

| Metric Name | Feasibility Assessment |
|------------|----------------------|
| **System Availability** | ⚠️ **Partially Feasible** - We can track if services are receiving requests, but we need to clarify what "system is up" means. Do we want to know if services are responding, or if they're receiving traffic? We may need additional monitoring setup to track service health status. |
| **SLA Compliance Rate** | ✅ **Feasible** - This metric is already being tracked. We can show SLA compliance rates, but need to know which specific SLA types (availability, response time, etc.) should be included in the calculation. |
| **Throughput (Requests per Second)** | ✅ **Feasible** - We can measure how many requests per second are being processed. The time window (1 minute, 5 minutes, etc.) can be adjusted based on what makes most sense for the dashboard. |
| **Critical Alerts/Red Flags Count** | ⚠️ **Partially Feasible** - We can count server errors (5xx errors), but need to define what makes an alert "critical". Is it based on error codes, number of errors, or specific alert conditions? We may need to set up alert rules to properly track this. |
| **Success Rate** | ✅ **Feasible** - We can calculate the percentage of successful requests (2xx status codes) out of all requests. This is similar to SLA Compliance but calculated in a different way. |
| **Failed Requests Count** | ✅ **Feasible** - We can count all failed requests (4xx and 5xx errors). We already have detailed error tracking, so this metric is available. |
| **Timeout Rate** | ⚠️ **Partially Feasible** - We can track requests that return timeout errors (504 status code), but need to clarify if timeouts should also include requests that take too long (even if they eventually complete). What duration should be considered a timeout? |
| **Concurrent Requests** | ❌ **Not Feasible** - We currently don't track how many requests are being processed at the same time. This would require adding new tracking capability to count active/in-progress requests. |
| **Queue Depth** | ❌ **Not Feasible** - We don't currently track queue depth. If the system uses queues to process requests, we would need to add monitoring to track how many items are waiting in the queue. |

---

## Usage & Adoption Metrics

| Metric Name | Feasibility Assessment |
|------------|----------------------|
| **Total API Requests (Daily/Monthly)** | ✅ **Feasible** - We can count total API requests for any time period (daily, weekly, monthly). The data is available and can be filtered by service type (OCR, TTS, ASR, etc.). |
| **Requests per Model (Daily Avg)** | ⚠️ **Partially Feasible** - We can show average requests per service type (OCR, TTS, ASR, etc.) per day, but we need to clarify: when you say "model", do you mean service types (like OCR, TTS) or specific model versions? We currently track by service type, not individual model versions. |
| **Top 5 Models by Usage** | ⚠️ **Partially Feasible** - We can show the top 5 service types by usage (OCR, TTS, ASR, etc.), but not individual model versions. Need to clarify if "model" means service type or specific model versions. |
| **Requests by Time of Day** | ⚠️ **Partially Feasible** - We can show request patterns throughout the day, but it requires some additional setup in the dashboard to group requests by hour. The heatmap visualization is possible but needs configuration. |
| **Peak Usage Hours** | ✅ **Feasible** - We can identify which hours have the highest request volume. This can be shown as a time series chart showing usage patterns throughout the day. |
| **Request Volume Trends (Week/Month)** | ✅ **Feasible** - We can show request volume trends over weeks or months, broken down by service type. This works well as a line chart showing growth or decline over time. |
| **API Version Usage Distribution** | ❌ **Not Feasible** - We don't currently track which API version customers are using. If API versioning is important, we would need to add tracking to capture this information from requests. |

---

## Customer Reach Metrics

| Metric Name | Feasibility Assessment |
|------------|----------------------|
| **Total Customers** | ✅ **Feasible** - We can count the total number of unique customers who have made requests. Customer identification comes from request headers or authentication tokens. |
| **Total Active Customers** | ✅ **Feasible** - We can count customers who have made requests in a specific time period (e.g., last 30 days). Need to clarify: what time period defines an "active" customer? |
| **Total Customers Using APIs by Service** | ✅ **Feasible** - We can show how many unique customers are using each service type (OCR, TTS, ASR, etc.). This shows customer adoption across different services. |
| **Top 10 Customers by Usage** | ✅ **Feasible** - We can identify and rank the top 10 customers by their request volume. This helps identify the most active customers. |
| **Unique Customers per Model** | ⚠️ **Partially Feasible** - We can show unique customers per service type (OCR, TTS, etc.), but not per individual model version. Need to clarify if "model" means service type or specific model versions. |
| **New Customers (Daily/Weekly/Monthly)** | ✅ **Feasible** - We can calculate new customers by comparing customer lists across different time periods. For example, customers who appeared in the last 24 hours but not in the previous 24 hours would be "new". |

---

## Growth Metrics

| Metric Name | Feasibility Assessment |
|------------|----------------------|
| **Growth Rate (MoM)** | ✅ **Feasible** - We can calculate month-over-month growth by comparing request volumes between the current month and previous month. This shows if usage is increasing or decreasing. |
| **Usage Growth by Model Type** | ⚠️ **Partially Feasible** - We can show growth by service type (OCR, TTS, etc.), but not by individual model versions. Need to clarify if "model" means service type or specific model versions. |

---

## Customer Health Metrics

| Metric Name | Feasibility Assessment |
|------------|----------------------|
| **Inactive Customers Count** | ✅ **Feasible** - We can identify customers who haven't made requests recently. Need to clarify: what defines an "inactive" customer? For example, customers who made requests 30-90 days ago but not in the last 30 days? |
| **Customer Retention Rate** | ✅ **Feasible** - We can calculate what percentage of customers from a previous period are still active in the current period. Need to clarify: should we compare customers active in both time periods, or use a different definition? |

---

## Resource Utilization Metrics

| Metric Name | Feasibility Assessment |
|------------|----------------------|
| **CPU Usage by Service** | ⚠️ **Partially Feasible** - We currently track overall system CPU usage, not per-service CPU. We can show CPU usage per customer/organization, but need to clarify: do you need CPU usage per service type (OCR, TTS, etc.) or per customer organization? |
| **Memory Usage by Service** | ⚠️ **Partially Feasible** - We currently track overall system memory usage, not per-service memory. We can show memory usage per customer/organization, but need to clarify: do you need memory usage per service type (OCR, TTS, etc.) or per customer organization? |
| **API Rate Limit Hits** | ⚠️ **Partially Feasible** - We can count requests that hit rate limits (429 status code), but need to clarify: are rate limits only indicated by this error code, or are there other ways the system indicates rate limiting (custom headers, different error codes)? |
| **Throttled Requests Count** | ⚠️ **Partially Feasible** - Similar to rate limit hits, we can count throttled requests if they return a 429 status code. Need to clarify how throttling is indicated in the system - is it always a 429 error, or are there other indicators? |

---

## Summary

### ✅ Ready to Implement (15 metrics)
These metrics can be built right away with the data we currently collect.

### ⚠️ Needs Clarification (12 metrics)
These metrics are possible but need product team input on definitions or requirements before we can build them.

### ❌ Requires Development (3 metrics)
These metrics need new tracking capabilities to be added to the system before they can be measured.

---

## Key Questions for Product Team

1. **Model vs Service Type**: When metrics refer to "model", do you mean:
   - Service types (OCR, TTS, ASR, etc.) - ✅ Available now
   - Individual model versions (v1.0, v2.0, etc.) - ❌ Not currently tracked

2. **Customer Definitions**:
   - What time period defines an "active" customer? (e.g., requests in last 30 days)
   - What defines an "inactive" customer? (e.g., no requests in last 30 days, but had requests 30-90 days ago)
   - How should "customer retention" be calculated?

3. **System Health**:
   - What does "system is up" mean? (responding to requests, receiving traffic, or both?)
   - What makes an alert "critical"?

4. **Timeouts**:
   - Should timeout rate include only requests that return timeout errors (504), or also requests that take longer than a certain duration?

5. **Resource Usage**:
   - Do you need CPU/memory usage per service type (OCR, TTS, etc.) or per customer organization?

6. **API Versioning**:
   - Is tracking API version usage important? If yes, we'll need to add this capability.

