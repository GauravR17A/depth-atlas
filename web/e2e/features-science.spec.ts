import { enterWorkspace, openTool } from './ux-helpers';
import {expect,test,type Page} from '@playwright/test';

async function openSearch(page:Page){
  await page.addInitScript(()=>Object.defineProperty(navigator,'connection',{value:{saveData:true},configurable:true}));
  await enterWorkspace(page);
  await openTool(page,'Open structure search');
  await expect(page.getByLabel('Structure search results',{exact:true})).toBeVisible({timeout:20000});
  await page.getByLabel('Structure graphics',{exact:true}).selectOption('basic');
}

async function queryDepth(page:Page,low:string,high:string){
  await page.getByLabel('Structure threshold',{exact:true}).fill('-100');
  await page.getByLabel('Minimum search depth',{exact:true}).fill(low);
  await page.getByLabel('Maximum search depth',{exact:true}).fill(high);
  const response=page.waitForResponse(r=>r.url().endsWith('/features/search')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Find regions',exact:true}).click();
  expect((await response).ok()).toBeTruthy();
  await expect(page.locator('.feature-result-header')).toContainText(`${low}\u2013${high} m`);
}

async function build(page:Page){
  await page.getByRole('button',{name:'Build section',exact:true}).click();
  await expect(page.getByRole('img',{name:'Vertical section along the drawn line'})).toBeVisible({timeout:20000});
}

test('a wholly missing source section has no invented numeric colour scale',async({page})=>{
  await openSearch(page);await queryDepth(page,'4500','5000');await build(page);
  await expect(page.getByLabel('Section colour scale',{exact:true})).toContainText('No finite source values. Hatching marks missing samples.');
  await expect(page.locator('.feature-section-view .feature-scale')).toHaveCount(0);
  await expect(page.getByLabel('Section source value',{exact:true})).toContainText('Missing in the source');
  const section=page.getByRole('img',{name:'Vertical section along the drawn line'});
  await expect(section.locator('rect[fill="url(#feature-missing)"]')).toHaveCount(81);
});

test('one repeated native value has a constant legend and preserves requested versus sampled coordinates',async({page})=>{
  await openSearch(page);await queryDepth(page,'300','301');
  await page.getByLabel('Section start longitude').fill('86');await page.getByLabel('Section start latitude').fill('13');
  await page.getByLabel('Section end longitude').fill('86.000001');await page.getByLabel('Section end latitude').fill('13.000001');
  await build(page);
  await expect(page.getByLabel('Section colour scale',{exact:true})).toContainText('Constant source value:');
  await expect(page.locator('.feature-section-view .feature-scale')).toHaveCount(0);
  await expect(page.locator('.feature-section-title')).toContainText('0.000155 km');
  const depthTicks=page.getByRole('img',{name:'Vertical section along the drawn line'}).locator('text[x="52"]');
  await expect(depthTicks).toHaveText(['300','300.25','300.5','300.75','301']);
  await expect(page.locator('.feature-line-identity')).toContainText('Displayed line A: 86');
  await expect(page.locator('.feature-line-identity')).toContainText('86.000001');
  await page.getByLabel('Section station',{exact:true}).selectOption('80');
  await expect(page.getByLabel('Section source value',{exact:true})).toContainText('Requested station: 86.000001');
  await expect(page.getByLabel('Section source value',{exact:true})).toContainText('Model column: 86');
  await page.getByLabel('Section end longitude').fill('89');
  await expect(page.getByLabel('Draw a question',{exact:true})).toContainText('The endpoint controls differ from the displayed section.');
  await expect(page.locator('.feature-line-identity')).toContainText('86.000001');
});

test('exact depth midpoints select the deeper source bin and the final cell edge is included',async({page})=>{
  await openSearch(page);await queryDepth(page,'0','337');await build(page);
  const svg=page.getByRole('img',{name:'Vertical section along the drawn line'});
  // Fix the event coordinate transform for this exact-boundary check. Browser
  // MouseEvent integer pixels otherwise round a scaled SVG boundary, making
  // the test depend on layout instead of the declared depth-bin convention.
  await svg.evaluate(element=>{
    const original=(element as SVGSVGElement).getScreenCTM;
    (element as SVGSVGElement).getScreenCTM=()=>new DOMMatrix();
    element.dispatchEvent(new MouseEvent('click',{bubbles:true,clientX:200,clientY:24}));
    (element as SVGSVGElement).getScreenCTM=original;
  });
  await expect(page.getByLabel('Section native depth',{exact:true})).toHaveValue('1');
  await expect(page.getByLabel('Section source value',{exact:true})).toContainText('Native model value at 2 m');
  await svg.evaluate(element=>{
    const original=(element as SVGSVGElement).getScreenCTM;
    (element as SVGSVGElement).getScreenCTM=()=>new DOMMatrix();
    element.dispatchEvent(new MouseEvent('click',{bubbles:true,clientX:200,clientY:348}));
    (element as SVGSVGElement).getScreenCTM=original;
  });
  await expect(page.getByLabel('Section source value',{exact:true})).toContainText('Native model value at 300 m');
});
