# ZenithWallArt — 100% Automated Digital Store

## 🤖 What This Does
- Customer visits your store, browses AI-described products
- Clicks Buy → Stripe checkout (100% automated)
- Payment confirmed → Claude API writes delivery message
- Email sent automatically with download link
- Order saved to Supabase database
- ZERO manual work required

---

## ⚡ Setup in 15 Minutes

### Step 1 — Stripe
1. Go to stripe.com → Create account
2. Dashboard → Developers → API Keys
3. Copy **Secret key** (sk_live_...) → paste in .env
4. Go to Webhooks → Add endpoint
   - URL: `https://your-domain.com/webhook`
   - Events: `checkout.session.completed`
5. Copy **Webhook signing secret** → paste in .env

### Step 2 — Supabase
1. Go to supabase.com → Create project
2. Go to SQL Editor → paste contents of `supabase-schema.sql` → Run
3. Go to Settings → API
4. Copy **Project URL** and **anon public key** → paste in .env

### Step 3 — Email (Gmail)
1. Google Account → Security → 2-Step Verification → ON
2. Security → App Passwords → Generate
3. Copy the 16-character password → paste in .env as EMAIL_PASS
4. Paste your Gmail address as EMAIL_USER

### Step 4 — Deploy
```bash
# Install dependencies
npm install

# Copy and fill in your .env
cp .env.example .env
nano .env   # paste all your keys

# Start the store
npm start
```

### Step 5 — Deploy to Render (Free Hosting)
1. Push this folder to GitHub
2. Go to render.com → New Web Service
3. Connect your GitHub repo
4. Add all .env variables in Render dashboard
5. Deploy → Get your URL → Update STORE_URL in .env

---

## 💰 Revenue Flow
```
Customer pays $8.99
↓
Stripe takes ~$0.56 (2.9% + $0.30)
↓
You receive $8.43 per sale
↓
100 sales/month = $843 passive income
```

---

## 🔑 Keys You Need
| Key | Where to Get |
|-----|-------------|
| STRIPE_SECRET_KEY | stripe.com → Developers → API Keys |
| STRIPE_WEBHOOK_SECRET | stripe.com → Webhooks |
| ANTHROPIC_API_KEY | console.anthropic.com |
| SUPABASE_URL | supabase.com → Settings → API |
| SUPABASE_ANON_KEY | supabase.com → Settings → API |
| EMAIL_USER | Your Gmail address |
| EMAIL_PASS | Gmail App Password |

---

## 📊 The Full Automation Flow
1. **Claude API** → generates product descriptions on hover
2. **Stripe** → handles all payments securely
3. **Claude API** → writes personalised delivery email
4. **Nodemailer** → sends email with download link instantly
5. **Supabase** → stores all orders and download tokens
6. **Express** → serves the store and handles webhooks

**You do nothing. The machine runs 24/7.**
