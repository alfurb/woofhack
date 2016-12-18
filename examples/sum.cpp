#include <iostream>

using namespace std;

int main() {
  int a, b;
  cin >> a >> b;
  cout << a + b;
  // Compile time error
  //char c
  // To make a run time error
  /*int* c = &a;
  delete c;*/
  return 0;
}
