#!/usr/bin/env node

/**
 * PDF生成脚本
 * 使用puppeteer将HTML转换为PDF
 */

const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

// Polyfill ReadableStream for older Node versions where it's not global
try {
  if (typeof global.ReadableStream === 'undefined') {
    const streamWeb = require('stream/web');
    if (streamWeb && streamWeb.ReadableStream) {
      global.ReadableStream = streamWeb.ReadableStream;
    } else {
      // Fallback to ponyfill if necessary
      global.ReadableStream = require('web-streams-polyfill/ponyfill').ReadableStream;
    }
  }
} catch (e) {
  try {
    global.ReadableStream = require('web-streams-polyfill/ponyfill').ReadableStream;
  } catch (_) {
    // Ignore; puppeteer may still work without stream usage depending on version
  }
}

async function generatePDF(htmlFilePath, outputPath) {
  let browser;
  
  try {
    console.log('Starting browser...');
    
    // 启动浏览器 - 优化启动参数
    browser = await puppeteer.launch({
      headless: true,
      timeout: 30000, // 30秒启动超时
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
        '--no-first-run',
        '--no-zygote',
        '--single-process',
        '--disable-extensions',
        '--disable-background-timer-throttling',
        '--disable-backgrounding-occluded-windows',
        '--disable-renderer-backgrounding',
        '--disable-features=TranslateUI',
        '--disable-ipc-flooding-protection',
        '--memory-pressure-off'
      ]
    });
    
    console.log('Browser started, creating page...');
    const page = await browser.newPage();
    
    // 设置视口
    await page.setViewport({
      width: 1200,
      height: 800,
      deviceScaleFactor: 1 // 降低设备像素比以提高性能
    });
    
    // 读取HTML内容
    console.log('Reading HTML content...');
    const htmlContent = fs.readFileSync(htmlFilePath, 'utf8');
    
    // 设置页面内容 - 简化等待策略
    console.log('Setting page content...');
    await page.setContent(htmlContent, { 
      waitUntil: 'domcontentloaded', // 只等待DOM加载完成
      timeout: 15000 // 减少超时时间
    });
    
    // 注入PDF专用CSS样式，确保所有内容都能完整显示并允许跨页
    await page.addStyleTag({
      content: `
        @media print {
          .logs-content {
            max-height: none !important;
            overflow-y: visible !important;
            height: auto !important;
            display: block !important;
          }
          .scenario-item {
            page-break-inside: auto !important;
            break-inside: auto !important;
            margin-bottom: 15px !important;
          }
          .dimension-group {
            page-break-inside: auto !important;
            break-inside: auto !important;
            margin-bottom: 25px !important;
          }
          .scenario-text {
            white-space: pre-wrap !important;
            word-wrap: break-word !important;
            max-width: none !important;
            overflow: visible !important;
          }
          /* 强制分页样式 */
          .page-break {
            page-break-after: always !important;
            break-after: page !important;
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            border: none !important;
            clear: both !important;
            display: block !important;
            visibility: hidden !important;
          }
        }
      `
    });
    
    // 简单等待一下让样式生效（兼容无 waitForTimeout 的环境）
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    // 生成PDF
    console.log('Generating PDF...');
    const pdf = await page.pdf({
      format: 'A4',
      printBackground: true,
      margin: {
        top: '0.5in',
        right: '0.5in',
        bottom: '0.5in',
        left: '0.5in'
      },
      preferCSSPageSize: true,
      displayHeaderFooter: false,
      timeout: 30000 // PDF生成超时
    });
    
    // 保存PDF
    console.log('Saving PDF...');
    fs.writeFileSync(outputPath, pdf);
    
    console.log(`PDF generated successfully: ${outputPath}`);
    return true;
    
  } catch (error) {
    console.error('Error generating PDF:', error);
    throw error;
  } finally {
    if (browser) {
      console.log('Closing browser...');
      await browser.close();
    }
  }
}

// 命令行参数处理
if (require.main === module) {
  const args = process.argv.slice(2);
  
  if (args.length !== 2) {
    console.error('Usage: node generate_pdf.js <html_file_path> <output_pdf_path>');
    process.exit(1);
  }
  
  const [htmlFilePath, outputPath] = args;
  
  // 检查输入文件是否存在
  if (!fs.existsSync(htmlFilePath)) {
    console.error(`HTML file not found: ${htmlFilePath}`);
    process.exit(1);
  }
  
  // 确保输出目录存在
  const outputDir = path.dirname(outputPath);
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }
  
  // 生成PDF
  generatePDF(htmlFilePath, outputPath)
    .then(() => {
      console.log('PDF generation completed successfully');
      process.exit(0);
    })
    .catch((error) => {
      console.error('PDF generation failed:', error);
      process.exit(1);
    });
}

module.exports = { generatePDF };