# FixDoc Website

Static landing page and demo showcase for FixDoc.

## Structure

```
fixdoc-web/
├── index.html          # Main landing page
├── demo.html           # Demo showcase with GIFs
├── waitlist.html       # Feedback/signup form
├── css/
│   └── styles.css      # Custom styles (extends Tailwind)
├── assets/
│   ├── logo.svg        # FixDoc logo
│   ├── demo-tour.gif   # Main demo walkthrough (TODO)
│   ├── terraform-capture.gif  # Capture flow (TODO)
│   └── search-flow.gif # Search workflow (TODO)
└── README.md           # This file
```

## Development

### Local Preview

Open `index.html` directly in your browser, or use a local server:

```bash
# Python 3
cd fixdoc-web
python -m http.server 8000

# Node.js (with npx)
npx serve .
```

Then visit `http://localhost:8000`

### Creating Demo GIFs

Tools for recording terminal GIFs:

**macOS:**
- [Gifox](https://gifox.io/) - Best quality, easy to use
- [Kap](https://getkap.co/) - Free, open source
- [LICEcap](https://www.cockos.com/licecap/) - Simple, lightweight

**Linux:**
- [Peek](https://github.com/phw/peek) - Easy screen recorder
- [Byzanz](https://github.com/GNOME/byzanz) - Command-line based

**Recommended settings:**
- Resolution: 800x500px
- Frame rate: 10-15 fps
- Duration: 15-30 seconds per GIF
- Font size: Large (easily readable)

**GIFs to create:**

1. **demo-tour.gif** - Full `fixdoc demo tour` walkthrough
   ```bash
   fixdoc demo seed
   fixdoc demo tour
   ```

2. **terraform-capture.gif** - Pipe Terraform error → capture
   ```bash
   terraform apply 2>&1 | fixdoc capture
   # Enter resolution when prompted
   ```

3. **search-flow.gif** - Search and show commands
   ```bash
   fixdoc search "access denied"
   fixdoc show 1
   ```

**Tips for good recordings:**
- Use a clean terminal with dark background
- Type slowly and deliberately
- Pause at key moments so viewers can read
- Optimize final GIFs (use [gifsicle](https://www.lcdf.org/gifsicle/) or online tools)

### Typeform Integration

The waitlist page includes a placeholder form. To use Typeform:

1. Create account at [typeform.com](https://www.typeform.com)
2. Create a form with these fields:
   - Email (required)
   - Primary use case (dropdown)
   - Pain points (long text)
   - Company size (dropdown)
   - Role (dropdown)
3. Get embed code from Typeform
4. Replace the form in `waitlist.html` with the embed

**Typeform embed example:**
```html
<div data-tf-live="YOUR_FORM_ID"></div>
<script src="//embed.typeform.com/next/embed.js"></script>
```

## Deployment

### Vercel (Recommended)

1. Push to GitHub
2. Connect repo to [Vercel](https://vercel.com)
3. Set root directory to `fixdoc-web`
4. Deploy automatically on push

### Netlify

1. Push to GitHub
2. Connect repo to [Netlify](https://netlify.com)
3. Set publish directory to `fixdoc-web`
4. Deploy

### GitHub Pages

1. Go to repo Settings → Pages
2. Set source to `main` branch, `/fixdoc-web` folder
3. Enable GitHub Pages

## Tech Stack

- **HTML5** - Semantic markup
- **Tailwind CSS** - Utility-first styling (via CDN)
- **Vanilla JS** - Form handling
- **No build step** - Just static files

## Customization

### Colors

Edit the Tailwind config in each HTML file's `<head>`:

```javascript
tailwind.config = {
    theme: {
        extend: {
            colors: {
                primary: '#2563eb',    // Blue
                secondary: '#1e40af',  // Darker blue
                accent: '#3b82f6',     // Light blue
                dark: '#0f172a',       // Background
            }
        }
    }
}
```

### Analytics

Add Plausible or simple-analytics before closing `</body>`:

```html
<!-- Plausible -->
<script defer data-domain="fixdoc.dev" src="https://plausible.io/js/plausible.js"></script>

<!-- or Simple Analytics -->
<script async defer src="https://scripts.simpleanalyticscdn.com/latest.js"></script>
```

## License

MIT - Same as FixDoc CLI
