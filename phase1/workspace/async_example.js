// Example using async/await

/**
 * Simulate an API call or any delayed asynchronous operation 
 * @param {number} ms - milliseconds to wait 
 */
function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function main() {
  console.log('Start of the main process (Sync)');

  // Wait for 2 seconds
  await delay(2000);
  console.log('Finished waiting after 2 seconds.');

  // Execute another async task while simulating work
  const result = await someAsyncFunction();
  console.log(`Another task finished. Result: ${result}`);

  console.log('End of the main process (Sync)');
}

function someAsyncFunction() {
    return new Promise(resolve => {
        setTimeout(() => {
            resolve("Data loaded successfully!");
        }, 1000);
    });
}

// Run the main asynchronous function
main();