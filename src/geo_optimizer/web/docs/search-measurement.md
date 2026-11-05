# Search Console and Bing connections

Verify your website in GEOSITION, open **First-party search data** in the workspace, and choose **Connect Google Search Console** or **Connect Bing Webmaster Tools**. Approve read-only access with the provider account that has access to the same verified domain. GEOSITION selects a matching property automatically and fetches a first report. The dashboard shows the last sync, an error state, and a disconnect button.

Google and Bing search traffic totals are not AI-only citations. Google returns web search clicks and impressions for the previous 30 days. Bing returns available cross-surface traffic history. Bing's AI Performance citation report is separate and is not included. Results are not comparable to sampled GEOSITION benchmarks.

## Administrator setup

1. Apply `supabase/migrations/005_search_connections.sql` to the production Supabase database. SQLite creates the table automatically for local deployments.
2. Set `GEOSITION_PUBLIC_BASE_URL` to the site's canonical HTTPS origin. Register Google and Bing OAuth web applications with callback URLs `https://YOUR-ORIGIN/api/v1/search-connections/callback/google` and `/bing` respectively. Enable the Search Console API in Google Cloud and configure the Google OAuth consent screen. Provider verification or test-user restrictions may apply.
3. Set `GEOSITION_GOOGLE_OAUTH_CLIENT_ID`, `GEOSITION_GOOGLE_OAUTH_CLIENT_SECRET`, `GEOSITION_BING_OAUTH_CLIENT_ID`, and `GEOSITION_BING_OAUTH_CLIENT_SECRET` as server environment variables.
4. Generate a Fernet key with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`, and set it as `GEOSITION_OAUTH_ENCRYPTION_KEY`. Keep this stable and secret: losing or changing it makes stored connections unreadable until users reconnect.
5. Set a long random `CRON_SECRET`. `vercel.json` schedules the authenticated sync daily at 06:00 UTC. Vercel invokes it only for production deployments. Deploy after setting the variables and applying the migration.

OAuth requests Google `webmasters.readonly` or Bing `webmaster.read`. Refresh tokens are encrypted before database storage and never returned to the browser; provider access tokens are temporary. Disconnect deletes the stored refresh token and cached result, but does not revoke the provider grant; revoke access in Google or Bing account settings if desired. Reconnect after provider access is revoked or when a sync reports an error.

[Google OAuth documentation](https://developers.google.com/identity/protocols/oauth2/web-server) · [Google Search Analytics API](https://developers.google.com/webmaster-tools/v1/searchanalytics/query) · [Bing OAuth documentation](https://learn.microsoft.com/en-us/bingwebmaster/oauth2) · [Vercel cron security](https://vercel.com/docs/cron-jobs/manage-cron-jobs)

An advanced one-time token form is also available for troubleshooting. Its token is not stored.

The commerce audit checks product structured data present on an audited page. It cannot verify a merchant account, product feed submission, live inventory, or whether any platform will surface the product. Missing review markup is not treated as a defect. For feed guidance see [Google product data](https://developers.google.com/search/docs/specialty/ecommerce/share-your-product-data-with-google) and [OpenAI product feeds](https://developers.openai.com/commerce/guides/get-started).
