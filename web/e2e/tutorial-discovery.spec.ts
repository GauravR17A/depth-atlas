import {test,expect,type Page} from '@playwright/test';
import {featureTours} from '../src/learning/featureTours';
import {lessons,coreCount} from '../src/learning/lessons';
const coach=(page:Page)=>page.locator('.learning-coach');
async function tour(page:Page,id:string){
 await page.goto('/');await page.getByRole('button',{name:'Explore extra feature tutorials'}).click();
 const picker=page.locator('.feature-tour-picker'),index=featureTours.findIndex(t=>t.id===id);
 for(let n=0;n<Math.floor(index/2);n++)await picker.getByRole('button',{name:'More features',exact:true}).click();
 await picker.getByRole('button',{name:`Start ${featureTours[index].title} tutorial`,exact:true}).click();
}
test('core follows the PS workflow and every extra-tour lesson exists',()=>{
 expect(lessons[0].id).toBe('globe');expect(lessons.slice(0,coreCount).map(l=>l.id)).toEqual(['globe','volume','cutaway','depth','slice','time','salinity','currents','iso','section','display','overlay','profile','compare','csv','netcdf','sources','save']);
 expect(new Set(lessons.map(l=>l.id)).size).toBe(lessons.length);
 for(const feature of featureTours)for(const id of feature.lessonIds)expect(lessons.some(l=>l.id===id)).toBe(true);
});
test('completion points to the real Tools control and opens the complete menu',async({page})=>{
 await tour(page,'imports');
 for(let n=0;n<2;n++){await expect(coach(page).getByLabel('Tutorial result')).toBeVisible();await coach(page).getByRole('button',{name:'Next',exact:true}).click();}
 await coach(page).getByRole('button',{name:'Explore on my own'}).click();
 const hint=page.getByRole('complementary',{name:'Find all tools'}),tools=page.locator('#workspace-tools');
 await expect(hint).toBeVisible();await expect(tools).toHaveAttribute('data-tutorial-control','');await expect(tools).toBeFocused();
 await expect.poll(()=>hint.evaluate(e=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth+1&&r.top>=0&&r.bottom<=innerHeight+1;})).toBe(true);
 expect(await hint.evaluate(e=>e.querySelector('p')!.getBoundingClientRect().bottom+6<=e.querySelector('.primary-button')!.getBoundingClientRect().top)).toBe(true);await expect(hint.locator('.learn-pointer')).toBeVisible();await hint.getByRole('button',{name:'Open Tools',exact:true}).click();
 await expect(page.getByRole('dialog',{name:'What would you like to find out?'})).toBeVisible();await expect(hint).toHaveCount(0);await expect(tools).not.toHaveAttribute('data-tutorial-control','');
 await expect(page.locator('.tool-menu .tool-card')).toHaveCount(12);
});
test('chlorophyll tour selects measured chlorophyll in March and saves the original only on request',async({page})=>{
 test.setTimeout(90000);let captures=0;page.on('request',r=>{if(r.url().includes('/api/investigations/capture'))captures++;});
 await tour(page,'chlorophyll');await expect(coach(page).getByLabel('Tutorial result')).toContainText('2024-03');await coach(page).getByRole('button',{name:'Next',exact:true}).click();
 await expect(coach(page).getByLabel('Tutorial result')).toBeVisible();await expect(page.getByLabel('Study case',{exact:true})).toHaveValue('bay-bengal-2024-03');
 await expect(page.getByLabel('Profile variable',{exact:true})).toHaveValue('chlorophyll');await coach(page).getByRole('button',{name:'Next',exact:true}).click();
 const saved=page.getByRole('dialog',{name:'Saved investigations'});await expect(saved.getByRole('note')).toBeVisible();expect(captures).toBe(0);
 await expect(saved.locator('.investigation-capture')).toContainText('original uploaded file');await saved.getByRole('button',{name:'Save on this browser',exact:true}).click();
 await expect(saved.getByRole('status')).toContainText('Saved on this browser',{timeout:45000});expect(captures).toBe(1);
 await expect(saved.getByRole('note')).toBeVisible();await expect(saved.getByRole('button',{name:'Offline viewer',exact:true})).toBeVisible();
 await saved.getByRole('button',{name:'Close form and continue tutorial'}).click();await expect(coach(page).getByRole('button',{name:'Next',exact:true})).toBeEnabled();
});
test('support tutorial shows the actual strict timing sensitivity',async({page})=>{
 await tour(page,'support');await expect(coach(page).getByLabel('Tutorial result')).toBeVisible();await expect(page.getByLabel('Structure support counts')).toContainText('34');
 await coach(page).getByRole('button',{name:'Next',exact:true}).click();await expect(coach(page).getByLabel('Tutorial result')).toBeVisible();
 await expect(page.getByLabel('Support sensitivity',{exact:true})).toContainText('Reference: +/- 6 h');await expect(page.getByLabel('Support time window')).toHaveValue('0');
 await expect(page.getByLabel('Structure support counts')).toContainText('0eligible pairs');await expect(coach(page)).toHaveAttribute('data-anchored','true');
});
test('failed publication tutorial offers retry without inventing a completed result',async({page})=>{
 await page.route('**/api/publication',route=>route.abort());await tour(page,'publication');await expect(coach(page).getByRole('button',{name:'Retry step'})).toBeVisible();await expect(coach(page).getByLabel('Tutorial result')).toHaveCount(0);
 await page.unroute('**/api/publication');await coach(page).getByRole('button',{name:'Retry step'}).click();await expect(coach(page).getByLabel('Tutorial result')).toContainText('Application');await expect(coach(page).getByRole('button',{name:'Next',exact:true})).toBeEnabled();
});
test('comparison tutorial recovers through Retry with real eligible pairs',async({page})=>{
 test.setTimeout(90000);
 await page.route('**/evidence/**',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{message:'Comparison request interrupted for recovery verification.'}})}));
 await page.goto('/');await page.getByRole('button',{name:'Start Basic tutorial',exact:true}).click();
 const index=lessons.findIndex(l=>l.id==='compare');await coach(page).locator('.learn-contents summary').click();await coach(page).getByRole('button',{name:`${index+1}. ${lessons[index].title}`,exact:true}).click();
 await expect(coach(page).getByRole('button',{name:'Retry step'})).toBeVisible();await expect(coach(page).getByLabel('Tutorial result')).toHaveCount(0);
 await page.unroute('**/evidence/**');await coach(page).getByRole('button',{name:'Retry step'}).click();
 await expect(coach(page).getByRole('button',{name:'Next',exact:true})).toBeEnabled({timeout:45000});await expect(page.getByLabel('Eligible comparison count')).toContainText('103 / 103');await expect(coach(page).getByLabel('Tutorial result')).toContainText('103');
});
