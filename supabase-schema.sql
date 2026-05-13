-- Run this in your Supabase SQL editor

CREATE TABLE orders (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  stripe_session_id text UNIQUE NOT NULL,
  product_id text NOT NULL,
  product_name text NOT NULL,
  customer_email text NOT NULL,
  amount integer NOT NULL,
  download_token text UNIQUE NOT NULL,
  expires_at timestamptz NOT NULL,
  status text DEFAULT 'completed',
  created_at timestamptz DEFAULT now()
);

-- Index for fast token lookup
CREATE INDEX idx_orders_token ON orders(download_token);
CREATE INDEX idx_orders_session ON orders(stripe_session_id);
CREATE INDEX idx_orders_email ON orders(customer_email);

-- Enable Row Level Security
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

-- Allow server to read/write (uses service role key on backend)
CREATE POLICY "Server full access" ON orders
  FOR ALL USING (true);
