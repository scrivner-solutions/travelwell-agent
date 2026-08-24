# TravelWell AI GitHub Actions Deployment Guide

This guide details the CI/CD configuration, required secrets, GCP permissions, deployment triggers, and rollback operations for TravelWell AI.

---

## 🔒 GitHub Secrets Configuration

To run the automated deployment workflow, configure the following secrets under **Settings > Secrets and variables > Actions** in your GitHub repository:

| Secret Name | Description | Example / Format |
| :--- | :--- | :--- |
| `GCP_PROJECT_ID` | The Google Cloud project ID. | `your-gcp-project-id` |
| `GCP_REGION` | Target deploy region for Cloud Run and Artifact Registry. | `us-central1` |
| `GCP_SA_KEY` | JSON Key credential string for the authorized Service Account. | `{"type": "service_account", ...}` |
| `GOOGLE_MAPS_API_KEY` | Backend Google Maps Platform credentials (Geocoding/Places/Routes). | `AIzaSy...` |

---

## 🛡️ Required GCP Service Account Roles

The GCP Service Account linked to `GCP_SA_KEY` must have sufficient permissions to push images to Artifact Registry and deploy revision changes to Cloud Run. Assign the following roles in IAM Console:

1.  **Artifact Registry Writer (`roles/artifactregistry.writer`):** Allows building and pushing Docker image tags to the `travelwell-images` repository.
2.  **Cloud Run Developer (`roles/run.developer`):** Allows deploying new revisions, managing services, and updating env parameters.
3.  **Service Account User (`roles/iam.serviceAccountUser`):** Required to run deployments utilizing the default Cloud Run execution identity service account (`travelwell-cloudrun-sa@...`).

---

## 🚀 Triggering Deployments

*   **Automation:** Push commits directly to the `main` branch. GitHub Actions catches the push event, runs code quality checks and unit tests via `uv`, compiles the React bundles, builds the container configurations, pushes image artifacts to Google Artifact Registry, and creates new Cloud Run revisions.
*   **Manual Trigger:** Go to the **Actions** tab on your GitHub repository, select **Deploy TravelWell AI** from the sidebar, and click **Run workflow** choosing the branch you want to deploy from.

---

## ⏪ Manual Rollback Procedures

If a deployment introduces issues, you can roll back to a previous revision instantly using `gcloud` or the GCP Console without rebuild steps:

### Option A: Using the Google Cloud Console (Recommended for Speed)
1. Navigate to the **Cloud Run** console in Google Cloud.
2. Select the service you want to revert (`travelwell-backend` or `travelwell-frontend`).
3. Click the **Revisions** tab.
4. Select the checkmark of the healthy historical revision (which was tagged with the specific GitHub SHA during build time).
5. Click **Manage Traffic** at the top.
6. Set the traffic routing percentage to `100%` for your chosen historical revision, and click **Save**.

### Option B: Using gcloud CLI
Run the following commands locally to shift traffic to a specific revision:

```bash
# Revert travelwell-backend
gcloud run services update-traffic travelwell-backend \
  --to-revisions=travelwell-backend-REVISION_NAME=100 \
  --region=your-gcp-region \
  --project=your-gcp-project-id

# Revert travelwell-frontend
gcloud run services update-traffic travelwell-frontend \
  --to-revisions=travelwell-frontend-REVISION_NAME=100 \
  --region=your-gcp-region \
  --project=your-gcp-project-id
```
*(Replace `REVISION_NAME` with the targeted historical revision string, e.g., `00008-brs`)*

---

## 🌐 Custom Domains & CORS Management

To route traffic via your production custom domains (`https://travelwellai.com` and `https://www.travelwellai.com`), ensure both domains are verified and mapped in the Google Cloud Console:

1. **Cloud Run Domain Mapping:**
   - Map `travelwellai.com` to the `travelwell-frontend` Cloud Run service.
   - Map `api.travelwellai.com` or backend custom endpoints to `travelwell-backend` if applicable.

2. **CORS Management via Environment Variables:**
   - By default, the backend allows standard development origins (localhost) and default Cloud Run service URLs.
   - To manage permitted domains without modifying code, configure the `CORS_ALLOWED_ORIGINS` environment variable on the `travelwell-backend` Cloud Run service.
   - **Format:** A comma-separated list of allowed origins.
     *Example:*
     `CORS_ALLOWED_ORIGINS=https://travelwellai.com,https://www.travelwellai.com,https://travelwell-frontend-163831374566.us-central1.run.app`
   - Update this variable directly in the Cloud Run service container settings or pass it via GitHub Actions secrets.

