# DeskMate Production Deployment Strategy (Azure & Enterprise Scaling)

This document details the production design architecture for deploying the DeskMate IT Helpdesk AI Assistant on Microsoft Azure, covering scaling, authentication, auditing, and enterprise-grade resiliency.

---

## 1. Containerization & App Hosting

### Dockerfile
For production deployment, the FastAPI backend and frontend assets are packaged into a single container image.

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and assets
COPY . .

# Run as non-privileged service user for safety
RUN useradd -m deskmateuser && chown -R deskmateuser:deskmateuser /app
USER deskmateuser

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

### Hosting Platform
The image is deployed to **Azure Container Apps (ACA)**:
- **Serverless Scaling**: ACA handles horizontal scaling automatically based on concurrent request counts or CPU/Memory utilization metrics.
- **VNet Integration**: Connects ACA directly to a secure corporate Azure Virtual Network, permitting private peering with MongoDB Atlas via Private Link.

---

## 2. Authentication & Authorization (Azure AD + JWT)

To transition from mock users to enterprise security:

- **Identity Management**: Integrate the application with **Microsoft Entra ID** (formerly Azure AD).
- **Access Tokens**: The frontend requests an OAuth 2.0 / OpenID Connect ID token from Microsoft Entra ID. It sends this token in the `Authorization: Bearer <JWT>` header of all requests to `/api/chat`.
- **JWT Verification**: FastAPI validates the token signature against Microsoft's public JWKS endpoints, extracts the employee's claims (such as `preferred_username` or `oid`), and overrides the client-submitted username context deterministically. This prevents spoofing attacks where employees could check or request entitlements for other users.

---

## 3. Auditing & Audit Logs (Cosmos DB / App Insights)

All tool calls, database modifications (ticket creations), and agent reasoning steps are captured and stored in a secure telemetry pipeline:

```
FastAPI Server ──► Azure Log Analytics Workspace ──► Azure Monitor / App Insights
    │
    └─► Azure Cosmos DB (NoSQL) for audit compliance
```

- **Compliance logs**: Record who executed the query, what tools were called (with inputs/outputs), and the timestamp.
- **Trace retention**: Store audit logs in Cosmos DB with a custom Time-To-Live (TTL) configuration (e.g. 7 years for enterprise compliance audits).

---

## 4. Rate Limiting per Employee

To prevent API abuse or denial-of-wallet scenarios (e.g., automated scripts calling the LLM backend repeatedly):

- Deploy **Azure API Management (APIM)** in front of the ACA ingress.
- Apply a rate-limiting policy mapped to the employee's identity claims:
  ```xml
  <rate-limit-by-key calls="100" duration="3600" counter-key="@(context.Request.Headers.GetValue("Authorization"))" increment-condition="@(context.Response.StatusCode == 200)" />
  ```
  This restricts each authenticated employee to 100 successful requests per hour.

---

## 5. Data Retention & Privacy

- **Ticket Data Retention**: IT tickets contain sensitive corporate requests. Define automated lifecycles (e.g., delete ticket contents 90 days after closure, retaining only anonymized metric summaries).
- **LLM Data Protection**: Employ Anthropic's commercial terms of service where input tokens and API requests are not used for model training or stored longer than 30 days.

---

## 6. Disaster Recovery & MongoDB Backup Strategy

- **Atlas Cloud Backup**: Enable continuous backups with Point-in-Time Recovery (PITR) in MongoDB Atlas across multiple regions.
- **Failover**: Configure MongoDB Atlas in a multi-region replica set. If an entire Azure region goes down, the cluster automatically promotes a secondary node in another region to primary, preserving service availability.

---

## 7. Key Operational Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| **Anthropic API Outage** | Critical | Implement multi-LLM failover in `agent.py`. If Claude API throws repeated connection errors, route requests automatically to an Azure OpenAI GPT-4o backup endpoint. |
| **Prompt Injection** | High | Use LLM Native function calling with strict input schemas. Keep system instructions separate from user messages. Employ Azure AI Content Safety filters on user queries. |
| **Stale Database Session** | Medium | Implement standard connection pooling and keepalive settings in the MongoDB driver (`maxPoolSize=50`, `retryWrites=true`). |
