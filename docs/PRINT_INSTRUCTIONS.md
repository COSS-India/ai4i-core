# How to Export PDF with Colors from Google Chrome

## Method 1: Using the HTML File (Recommended)

1. Open the file `casbin-rbac-print.html` in Google Chrome
2. Press `Ctrl+P` (or `Cmd+P` on Mac) to open Print dialog
3. **IMPORTANT:** In the Print dialog:
   - **Destination:** Select "Save as PDF"
   - **More settings** → Check **"Background graphics"** (this is crucial!)
   - **More settings** → Uncheck "Headers and footers" (optional)
4. Click "Save" and choose location

## Method 2: Direct from Markdown Preview

1. Open `casbin-rbac.md` in VS Code
2. Right-click on the preview → "Open Preview to the Side"
3. Right-click in the preview → "Open in Browser"
4. In Chrome, press `Ctrl+P`
5. **Enable "Background graphics"** in print settings
6. Save as PDF

## Method 3: Chrome Settings (If colors still don't show)

1. Open Chrome Settings (`chrome://settings/`)
2. Go to "Advanced" → "Printing"
3. Enable "Print background colors and images"
4. Then follow Method 1 or 2

## Troubleshooting

If colors still don't appear:
- Make sure "Background graphics" is checked in print dialog
- Try using the HTML file (`casbin-rbac-print.html`) instead of markdown
- Check Chrome version (should be recent)
- Try printing to PDF from a different browser (Firefox, Edge)

## Alternative: Use Online Tools

1. Upload `casbin-rbac.md` to an online markdown-to-PDF converter
2. Use tools like:
   - https://www.markdowntopdf.com/
   - https://md2pdf.netlify.app/
   - VS Code extension: "Markdown PDF"




