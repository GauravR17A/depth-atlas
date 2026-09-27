// Diagnostic only. Normal acceptance uses playwright.config.ts and the browser's
// default transport. A pass here does not certify normal HTTP/2 operation.
import {defineConfig} from '@playwright/test';
import base from './playwright.config';
export default defineConfig({...base,projects:base.projects?.map(project=>({...project,use:{...project.use,launchOptions:{args:['--disable-http2']}}}))});
