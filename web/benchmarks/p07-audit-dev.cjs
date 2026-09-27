const path=require('node:path');
(async()=>{
 const {createServer}=await import('../node_modules/vite/dist/node/index.js');
 const server=await createServer({configFile:path.resolve(__dirname,'../vite.config.ts'),root:path.resolve(__dirname,'..'),server:{host:'127.0.0.1',port:5174,strictPort:true,proxy:{'/api':{target:process.env.OCEAN_API_URL||'http://127.0.0.1:8004',changeOrigin:false}}}});
 await server.listen();server.printUrls();
})();
