import {test,expect} from '@playwright/test';
import {featureTours} from '../src/learning/featureTours';

// Final release contact sheet: real first results from each feature's own guide.
// Numerical and multi-step acceptance remain in the existing scientific suites.
for(const [index,tour] of featureTours.entries())test(`P17 visual: ${tour.title}`,async({page},info)=>{
 test.setTimeout(90000);const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');await page.getByRole('button',{name:'Explore extra feature tutorials'}).click();
 const picker=page.locator('.feature-tour-picker');
 for(let n=0;n<Math.floor(index/2);n++)await picker.getByRole('button',{name:'More features',exact:true}).click();
 await picker.getByRole('button',{name:`Start ${tour.title} tutorial`,exact:true}).click();
 const coach=page.locator('.learning-coach');await expect(coach.getByLabel('Tutorial result')).toBeVisible({timeout:60000});
 await expect(coach).toHaveAttribute('data-anchored','true');
 await page.screenshot({path:info.outputPath(`${tour.id}.png`),fullPage:true});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
 expect(await coach.evaluate(e=>{const r=e.getBoundingClientRect();return r.top>=0&&r.left>=0&&r.bottom<=innerHeight+1&&r.right<=innerWidth+1;})).toBe(true);
 expect(errors).toEqual([]);
});
