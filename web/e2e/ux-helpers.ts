import { expect, type Page } from '@playwright/test';

export async function dismissIntroduction(page:Page){
  if(!page.url().includes('#investigation='))await page.getByRole('button',{name:'Skip tutorial',exact:true}).click();
}
export async function enterWorkspace(page:Page,url='/'){
  await page.goto(url);
  await dismissIntroduction(page);
  if(!page.url().includes('#investigation='))await page.getByRole('button',{name:'Open 3D ocean',exact:true}).click();
}
export async function openTool(page:Page,name:string){
  await page.getByRole('button',{name:'Tools',exact:true}).click();
  await page.getByRole('button',{name,exact:true}).click();
}
export async function displaySettings(page:Page){
  const details=page.locator('.ocean-settings');
  if(await details.getAttribute('open')===null)await details.locator('summary').click();
  await expect(page.getByLabel('Graphics quality')).toBeVisible();
}
export async function extraView(page:Page,name:string){
  await page.getByRole('button',{name:'More views',exact:true}).click();
  await page.getByRole('button',{name,exact:true}).click();
}
