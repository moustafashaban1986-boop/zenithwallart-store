require('dotenv').config();
const express = require('express');
const cors = require('cors');
const path = require('path');

const app = express();
app.use(cors());
app.use('/webhook', express.raw({ type: 'application/json' }));
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// Lazy-load clients so server starts even without env vars
function getStripe() { return require('stripe')(process.env.STRIPE_SECRET_KEY); }
function getSupabase() { const { createClient } = require('@supabase/supabase-js'); return createClient(process.env.SUPABASE_URL, process.env.SUPABASE_ANON_KEY); }
function getAnthropic() { const Anthropic = require('@anthropic-ai/sdk'); return new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY }); }

// ─── PRODUCTS ──────────────────────────────────────────────────────────────
const PRODUCTS = [
  { id: 'golden-hour',    name: 'Golden Hour Abstract',      price: 899,  style: 'warm gold, terracotta, ivory abstract',     tag: 'Bestseller' },
  { id: 'midnight-ocean', name: 'Midnight Ocean Waves',      price: 799,  style: 'deep navy, teal, silver abstract ocean',    tag: 'New' },
  { id: 'forest-zen',     name: 'Forest Zen Botanicals',     price: 699,  style: 'sage green, cream, earthy botanical',       tag: null },
  { id: 'rose-marble',    name: 'Rose Marble Luxe',          price: 999,  style: 'blush pink, gold, white marble abstract',   tag: 'Premium' },
  { id: 'nordic-frost',   name: 'Nordic Frost Minimal',      price: 699,  style: 'ice white, grey, minimal Scandinavian',     tag: null },
  { id: 'sunset-boho',    name: 'Sunset Boho Dreams',        price: 799,  style: 'rust orange, mustard, desert bohemian',     tag: 'Popular' },
  { id: 'midnight-flora', name: 'Midnight Flora',            price: 899,  style: 'black, gold, botanical line art',           tag: null },
  { id: 'azure-coast',    name: 'Azure Coastal Breeze',      price: 749,  style: 'sky blue, white, soft coastal watercolor',  tag: 'New' },
];

// ─── API: PRODUCTS ─────────────────────────────────────────────────────────
app.get('/api/products', (req, res) => {
  res.json(PRODUCTS.map(p => ({ ...p, displayPrice: `$${(p.price/100).toFixed(2)}` })));
});

// ─── API: AI PREVIEW ───────────────────────────────────────────────────────
app.post('/api/generate-preview', async (req, res) => {
  const { productId } = req.body;
  const product = PRODUCTS.find(p => p.id === productId);
  if (!product) return res.status(404).json({ error: 'Not found' });
  try {
    const anthropic = getAnthropic();
    const msg = await anthropic.messages.create({
      model: 'claude-haiku-4-5-20251001', max_tokens: 300,
      messages: [{ role: 'user', content: `Write a compelling 2-sentence product description for a digital wall art print called "${product.name}". Style: ${product.style}. Make it luxurious and desirable. No markdown.` }]
    });
    res.json({ description: msg.content[0].text });
  } catch (e) { res.status(500).json({ error: e.message }); }
});

// ─── API: CHECKOUT ─────────────────────────────────────────────────────────
app.post('/api/checkout', async (req, res) => {
  const { productId, customerEmail } = req.body;
  const product = PRODUCTS.find(p => p.id === productId);
  if (!product) return res.status(404).json({ error: 'Not found' });
  try {
    const stripe = getStripe();
    const session = await stripe.checkout.sessions.create({
      payment_method_types: ['card'],
      customer_email: customerEmail || undefined,
      line_items: [{ price_data: { currency: 'usd', product_data: { name: `${product.name} — Digital Wall Art Print`, description: `Instant download • 5 sizes included • 300 DPI print-ready files` }, unit_amount: product.price }, quantity: 1 }],
      mode: 'payment',
      success_url: `${process.env.STORE_URL}/success?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${process.env.STORE_URL}`,
      metadata: { productId: product.id },
    });
    res.json({ url: session.url });
  } catch (e) { res.status(500).json({ error: e.message }); }
});

// ─── STRIPE WEBHOOK ────────────────────────────────────────────────────────
app.post('/webhook', async (req, res) => {
  const sig = req.headers['stripe-signature'];
  let event;
  try { event = getStripe().webhooks.constructEvent(req.body, sig, process.env.STRIPE_WEBHOOK_SECRET); }
  catch (err) { return res.status(400).send(`Webhook Error: ${err.message}`); }

  if (event.type === 'checkout.session.completed') {
    const session = event.data.object;
    const productId = session.metadata.productId;
    const customerEmail = session.customer_email;
    const product = PRODUCTS.find(p => p.id === productId);
    try {
      const downloadToken = require('crypto').randomBytes(32).toString('hex');
      const expiresAt = new Date(Date.now() + 7*24*60*60*1000).toISOString();
      await getSupabase().from('orders').insert({ stripe_session_id: session.id, product_id: productId, product_name: product.name, customer_email: customerEmail, amount: session.amount_total, download_token: downloadToken, expires_at: expiresAt, status: 'completed', created_at: new Date().toISOString() });
      const anthropic = getAnthropic();
      const artMsg = await anthropic.messages.create({ model: 'claude-haiku-4-5-20251001', max_tokens: 200, messages: [{ role: 'user', content: `Write a warm 2-sentence message for a customer who just purchased "${product.name}" digital wall art. Tell them what they received and how to print it. Be warm and professional.` }] });
      await sendEmail(customerEmail, product, `${process.env.STORE_URL}/download/${downloadToken}`, artMsg.content[0].text);
      console.log(`✅ Order: ${customerEmail} → ${product.name}`);
    } catch (err) { console.error('Order error:', err.message); }
  }
  res.json({ received: true });
});

// ─── DOWNLOAD ──────────────────────────────────────────────────────────────
app.get('/download/:token', async (req, res) => {
  const { data: order } = await getSupabase().from('orders').select('*').eq('download_token', req.params.token).single();
  if (!order) return res.status(404).send('Link not found.');
  if (new Date(order.expires_at) < new Date()) return res.status(410).send('Link expired.');
  res.send(`<!DOCTYPE html><html><head><title>Download — ${order.product_name}</title><style>body{font-family:Georgia,serif;background:#0a0a0f;color:#f0ede8;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}.box{max-width:500px;text-align:center;padding:3rem;border:1px solid rgba(201,169,110,0.3)}h1{font-size:1.8rem;color:#c9a96e;margin-bottom:1rem}p{line-height:1.8;color:rgba(240,237,232,0.7)}.btn{display:inline-block;background:#c9a96e;color:#0a0a0f;padding:1rem 2rem;text-decoration:none;margin-top:2rem;font-weight:bold}</style></head><body><div class="box"><h1>✨ ${order.product_name}</h1><p>Your print-ready files are ready! 5 high-resolution sizes (300 DPI) included.</p><p style="font-size:0.85rem;margin-top:1rem">Files: 5×7 | 8×10 | 11×14 | 16×20 | 18×24 inches</p><a href="#" class="btn">⬇ Download Your Art Files</a></div></body></html>`);
});

// ─── EMAIL ─────────────────────────────────────────────────────────────────
async function sendEmail(to, product, downloadUrl, aiMessage) {
  const nodemailer = require('nodemailer');
  const transporter = nodemailer.createTransport({ host: 'smtp.gmail.com', port: 587, secure: false, auth: { user: process.env.EMAIL_USER, pass: process.env.EMAIL_PASS } });
  await transporter.sendMail({
    from: `"ZenithWallArt" <${process.env.EMAIL_USER}>`, to,
    subject: `✨ Your "${product.name}" is ready!`,
    html: `<div style="font-family:Georgia,serif;background:#0a0a0f;color:#f0ede8;padding:3rem;max-width:600px;margin:0 auto"><h1 style="color:#c9a96e">Your Art is Ready! ✨</h1><p style="line-height:1.8;color:rgba(240,237,232,0.8)">${aiMessage}</p><div style="margin:2rem 0;padding:1.5rem;border:1px solid rgba(201,169,110,0.3)"><p style="color:#c9a96e;margin:0 0 0.5rem">What's included:</p><p style="margin:0;color:rgba(240,237,232,0.7)">5 print-ready JPG files • 300 DPI • Sizes: 5×7, 8×10, 11×14, 16×20, 18×24"</p></div><a href="${downloadUrl}" style="display:inline-block;background:#c9a96e;color:#0a0a0f;padding:1rem 2.5rem;text-decoration:none;font-weight:bold">⬇ Download Your Files</a><p style="margin-top:2rem;font-size:0.8rem;color:rgba(240,237,232,0.4)">Link expires in 7 days. ZenithWallArt — Premium Digital Prints</p></div>`
  });
}

// ─── START ─────────────────────────────────────────────────────────────────
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`🚀 ZenithWallArt running on port ${PORT}`));
